import os
import logging
import requests
import threading
import time as time_module
import pandas as pd
from flask import Flask, request, jsonify, render_template, redirect, url_for, render_template_string
from datetime import datetime, timedelta
import traceback
from bs4 import BeautifulSoup
from pybaseball import statcast
from sqlalchemy import create_engine, text
from simple_db_swordfinder import SimpleDatabaseSwordFinder
from models_complete import create_tables, get_db, SwordSwing, StatcastPitch
from video_downloader import process_sword_videos, get_download_stats, download_sword_clip, get_video_url_from_sporty_page

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Initialize database tables
# create_tables()  # Tables already exist in local database

# Initialize database-powered sword finder with your authentic MLB data
db_sword_finder = SimpleDatabaseSwordFinder()  # Uses your 226,833 authentic records

# Global status tracking for patch process
patch_status = {
    "status": "Idle",
    "rows_scanned": 0,
    "rows_updated": 0,
    "current_processing": "",
    "start_time": None,
    "elapsed_time": 0,
    "error_message": "",
    "total_expected": 0
}

@app.before_request
def force_https():
    """Redirect all HTTP traffic to HTTPS"""
    if (request.headers.get('X-Forwarded-Proto', 'http') == 'http' and 
        not app.debug and 
        'localhost' not in request.host and 
        '127.0.0.1' not in request.host):
        return redirect(request.url.replace('http://', 'https://'), code=301)

def get_best_video_url(play_id):
    """
    Try different video types in order and return the best available video URL
    
    Args:
        play_id (str): The UUID playId for the pitch
        
    Returns:
        dict: Contains playId, video_type, and video_url if successful, None otherwise
    """
    video_types = ["HOME", "AWAY", "NETWORK"]
    
    for video_type in video_types:
        video_url = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}&videoType={video_type}"
        
        try:
            logger.debug(f"Checking video URL: {video_url}")
            response = requests.get(video_url, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Found working video: {video_type} for playId {play_id}")
                return {
                    "playId": play_id,
                    "video_type": video_type,
                    "video_url": video_url
                }
            else:
                logger.debug(f"Video type {video_type} returned status {response.status_code}")
                
        except requests.RequestException as e:
            logger.warning(f"Error checking video type {video_type}: {str(e)}")
            continue
    
    logger.warning(f"No working video found for playId {play_id}")
    return None

@app.route('/')
def home():
    """Serve the main SwordFinder application"""
    return render_template('home.html')

@app.route('/docs')
def docs():
    """Serve the API documentation and testing interface"""
    return render_template('docs.html')

@app.route('/swords', methods=['POST'])
def find_swords():
    """
    Main API endpoint to find sword swings for a given date
    
    Expected JSON payload:
    {
        "date": "YYYY-MM-DD"
    }
    
    Returns:
    {
        "success": true,
        "data": [
            {
                "player_name": "Name",
                "pitch_type": "SL",
                "bat_speed": 45.8,
                "intercept_y": 23.2,
                "sword_score": 96.4,
                "play_id": "...",
                "game_pk": ...
            }
        ],
        "count": 5,
        "date": "2024-01-01"
    }
    """
    try:
        # Validate request content type
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Content-Type must be application/json"
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        if not data or 'date' not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: 'date'"
            }), 400
        
        date_str = data['date']
        
        # Validate date format
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date format. Use YYYY-MM-DD"
            }), 400
        
        # Check if date is not in the future
        if date_obj.date() > datetime.now().date():
            return jsonify({
                "success": False,
                "error": "Cannot analyze future dates"
            }), 400
        
        logger.info(f"Processing sword swing analysis for date: {date_str}")
        
        # Use database-powered version with complete authentic MLB data
        result = db_sword_finder.find_sword_swings(date_str)
        swords_from_finder = result.get('data', []) # Renamed to avoid confusion
        
        # Ensure SwordSwing records exist or are created for these swords
        # This list will hold the sword dictionaries that are passed to the video download loop and final response
        sword_dicts_for_processing = [] 

        with get_db() as db_session:
            for temp_sword_dict in swords_from_finder:
                statcast_pitch_id = temp_sword_dict.get('statcast_pitch_db_id')
                current_sword_score = temp_sword_dict.get('sword_score')

                if not statcast_pitch_id:
                    logger.warning("Sword data from finder missing statcast_pitch_db_id. Skipping SwordSwing table interaction.")
                    sword_dicts_for_processing.append(temp_sword_dict) # Add to list for response
                    continue

                sword_swing_orm_record = db_session.query(SwordSwing).filter(SwordSwing.pitch_id == statcast_pitch_id).first()

                if not sword_swing_orm_record:
                    logger.info(f"Creating new SwordSwing record for pitch_id {statcast_pitch_id} with score {current_sword_score}")
                    sword_swing_orm_record = SwordSwing(
                        pitch_id=statcast_pitch_id,
                        sword_score=current_sword_score, # This is the universally scaled score
                        raw_sword_metric=temp_sword_dict.get('raw_sword_metric'), # Store the raw metric
                        is_sword_swing=True
                    )
                    db_session.add(sword_swing_orm_record)
                    try:
                        db_session.commit() # Commit new SwordSwing record
                    except Exception as e:
                        db_session.rollback()
                        logger.error(f"Error creating SwordSwing for pitch_id {statcast_pitch_id}: {e}")
                        sword_dicts_for_processing.append(temp_sword_dict) 
                        continue 
                else: # SwordSwing record exists, update it
                    if sword_swing_orm_record.sword_score != current_sword_score:
                        logger.info(f"Updating sword_score for existing SwordSwing pitch_id {statcast_pitch_id} from {sword_swing_orm_record.sword_score} to {current_sword_score}")
                        sword_swing_orm_record.sword_score = current_sword_score
                    
                    # Also update raw_sword_metric if it's different or not set
                    # (assuming raw_sword_metric from finder is the source of truth for this request)
                    new_raw_metric = temp_sword_dict.get('raw_sword_metric')
                    if sword_swing_orm_record.raw_sword_metric != new_raw_metric and new_raw_metric is not None:
                        logger.info(f"Updating raw_sword_metric for existing SwordSwing pitch_id {statcast_pitch_id} from {sword_swing_orm_record.raw_sword_metric} to {new_raw_metric}")
                        sword_swing_orm_record.raw_sword_metric = new_raw_metric
                    
                    try:
                        # Only commit if there were changes to sword_score or raw_sword_metric
                        if db_session.is_modified(sword_swing_orm_record):
                            db_session.commit() 
                    except Exception as e:
                        db_session.rollback()
                        logger.error(f"Error updating score/raw_metric for SwordSwing pitch_id {statcast_pitch_id}: {e}")
                
                sword_dicts_for_processing.append(temp_sword_dict) # This dict goes to video processing and response

        # Batter name lookup and Video processing loop
        for i, sword_dict_for_response in enumerate(sword_dicts_for_processing[:5]):  # Only process top 5
            
            # Fetch Batter Name using batter_id
            batter_mlbam_id = sword_dict_for_response.get('batter_id')
            batter_name_str = f"Batter ID: {batter_mlbam_id}" # Default
            if batter_mlbam_id:
                try:
                    api_url = f"https://statsapi.mlb.com/api/v1/people/{batter_mlbam_id}"
                    response = requests.get(api_url, timeout=5)
                    response.raise_for_status()
                    batter_data = response.json()
                    if batter_data.get("people") and len(batter_data["people"]) > 0:
                        batter_name_str = batter_data["people"][0].get("fullName", batter_name_str)
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Could not fetch batter name for ID {batter_mlbam_id}: {e}")
                except ValueError: 
                    logger.warning(f"Could not parse JSON for batter ID {batter_mlbam_id}")
            sword_dict_for_response['batter_name'] = batter_name_str

            # Video processing logic starts here
            play_id = sword_dict_for_response.get('play_id') # play_id from simple_db_swordfinder (might be None)
            
            # If no play_id from simple_db_swordfinder, try to look it up using MLB Stats API
            # Use sword_dict_for_response here instead of undefined 'sword'
            if not play_id and sword_dict_for_response.get('game_pk') and sword_dict_for_response.get('inning') and sword_dict_for_response.get('pitch_number'):
                logger.info(f"Looking up playId for game {sword_dict_for_response['game_pk']}, inning {sword_dict_for_response['inning']}, pitch {sword_dict_for_response['pitch_number']}")
                
                try:
                    # Use MLB Stats API to get play ID
                    mlb_api_url = f"https://statsapi.mlb.com/api/v1.1/game/{sword_dict_for_response['game_pk']}/feed/live"
                    response = requests.get(mlb_api_url, timeout=10)
                    
                    if response.status_code == 200:
                        game_data = response.json()
                        all_plays = game_data['liveData']['plays']['allPlays']
                        
                        # Search for matching pitch using at-bat number
                        at_bat_counter = 0
                        for play in all_plays:
                            at_bat_counter += 1
                            
                            # Match by at-bat number
                            if at_bat_counter == sword_dict_for_response['at_bat_number']: # Use sword_dict_for_response
                                for event in play.get('playEvents', []):
                                    if event.get('pitchNumber') == sword_dict_for_response['pitch_number']: # Use sword_dict_for_response
                                        # Verify it's a swinging strike
                                        description = event.get('details', {}).get('description', '')
                                        if 'swinging' in description.lower():
                                            # Found it! Get the UUID play ID
                                            play_id_from_api = ( # Use a temporary variable
                                                event.get('playId') or
                                                event.get('uuid') or
                                                event.get('guid') or
                                                play.get('playId') or
                                                play.get('about', {}).get('playId')
                                            )
                                            
                                            if play_id_from_api: # play_id is updated here if found
                                                logger.info(f"Found playId for at-bat {sword_dict_for_response['at_bat_number']}, pitch {sword_dict_for_response['pitch_number']}: {play_id_from_api}")
                                                sword_dict_for_response['play_id'] = play_id_from_api # Update the dict that goes into the response
                                                play_id = play_id_from_api # Update the local play_id variable for this iteration
                                                break
                                
                                if play_id_from_api: # Check the temp variable
                                    break 
                                    
                except Exception as e:
                    logger.warning(f"Failed to lookup playId: {str(e)}")
            
            # After play_id is potentially updated in sword_dict_for_response, construct its video_url
            if play_id and isinstance(play_id, str) and play_id.strip():
                sword_dict_for_response['video_url'] = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id.strip()}&videoType=AWAY"
            else:
                sword_dict_for_response['video_url'] = None

            # Now try to download video if we have a valid play_id (either from simple_db_swordfinder or MLB API lookup)
            if play_id and not sword_dict_for_response.get('local_path'): 
                try:
                    download_url = get_video_url_from_sporty_page(play_id)
                    
                    if download_url:
                        video_download_outcome = download_sword_clip(play_id, download_url)
                        
                        if video_download_outcome:
                            sword_dict_for_response['local_mp4_path'] = video_download_outcome['path'].lstrip('/')
                            sword_dict_for_response['mp4_downloaded'] = True
                            
                            # Store in database using the SwordSwing ORM record
                            # Re-fetch the SwordSwing record within a new session scope for this update
                            with get_db() as db_session_update:
                                statcast_pitch_id_for_update = sword_dict_for_response.get('statcast_pitch_db_id')
                                if statcast_pitch_id_for_update:
                                    sword_swing_to_update = db_session_update.query(SwordSwing).filter(SwordSwing.pitch_id == statcast_pitch_id_for_update).first()
                                    if sword_swing_to_update:
                                        sword_swing_to_update.local_mp4_path = video_download_outcome['path']
                                        sword_swing_to_update.mp4_downloaded = True
                                        sword_swing_to_update.download_url = download_url # Direct MP4 link
                                        # Also save the Savant page video_url that was constructed for the API response
                                        if sword_dict_for_response.get('video_url'):
                                            sword_swing_to_update.video_url = sword_dict_for_response['video_url']
                                        
                                        sword_swing_to_update.updated_at = datetime.utcnow()
                                        try:
                                            db_session_update.commit()
                                            logger.info(f"Updated SwordSwing record for pitch_id {statcast_pitch_id_for_update} with video path.")
                                        except Exception as db_err_update:
                                            db_session_update.rollback()
                                            logger.error(f"Error committing video path update for SwordSwing pitch_id {statcast_pitch_id_for_update}: {db_err_update}")
                                    else:
                                        # This should ideally not happen if the creation step above worked
                                        logger.warning(f"Could not find SwordSwing record for pitch_id {statcast_pitch_id_for_update} during video path update.")
                                else:
                                    logger.warning(f"Missing statcast_pitch_db_id in sword data for play_id {play_id}, cannot update SwordSwing video path.")
                            
                            logger.info(f"Downloaded video {i+1}/5 for {date_str}: {play_id}")
                        else:
                            logger.warning(f"Failed to download video for {play_id}")
                            sword_dict_for_response['mp4_downloaded'] = False
                    else:
                        logger.warning(f"No download URL found for {play_id}")
                        sword_dict_for_response['mp4_downloaded'] = False
                        
                except Exception as e:
                    logger.error(f"Error downloading video for {play_id}: {str(e)}")
                    sword_dict_for_response['mp4_downloaded'] = False
            elif sword_dict_for_response.get('local_path'): 
                sword_dict_for_response['local_mp4_path'] = sword_dict_for_response['local_path'].lstrip('/')
                sword_dict_for_response['mp4_downloaded'] = True
        
        return jsonify({
            "success": True,
            "data": sword_dicts_for_processing, # Use the list that was iterated over
            "count": len(sword_dicts_for_processing),
            "date": date_str
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.route('/playid', methods=['POST'])
def get_play_id():
    """
    Look up playId for a specific pitch using MLB Stats API
    
    Expected JSON payload:
    {
        "game_pk": 777788,
        "pitch_number": 4,
        "inning": 2
    }
    
    Returns:
    {
        "success": true,
        "playId": "0c0bea6e-cfce-326c-b224-4840f872c7c8",
        "video_url": "https://baseballsavant.mlb.com/sporty-videos?playId=...&videoType=AWAY"
    }
    """
    try:
        # Validate request content type
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Content-Type must be application/json"
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['game_pk', 'pitch_number', 'inning']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: '{field}'"
                }), 400
        
        game_pk = data['game_pk']
        pitch_number = data['pitch_number']
        inning = data['inning']
        
        logger.info(f"Looking up playId for game {game_pk}, inning {inning}, pitch {pitch_number}")
        
        # Call MLB Stats API
        mlb_api_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        
        try:
            response = requests.get(mlb_api_url, timeout=10)
            response.raise_for_status()
            game_data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch game data from MLB API: {e}")
            return jsonify({
                "success": False,
                "error": f"Failed to fetch game data: {str(e)}"
            }), 500
        
        # Parse liveData.plays.allPlays
        try:
            all_plays = game_data['liveData']['plays']['allPlays']
            # Debug: log the structure of the first play
            if len(all_plays) > 0:
                first_play = all_plays[0]
                logger.debug(f"First play keys: {list(first_play.keys())}")
                logger.debug(f"First play sample: {dict(list(first_play.items())[:5])}")
        except KeyError as e:
            logger.error(f"Unexpected MLB API response structure: {e}")
            return jsonify({
                "success": False,
                "error": "Unexpected game data structure from MLB API"
            }), 500
        
        # Search for matching pitch
        logger.debug(f"Searching through {len(all_plays)} plays")
        
        for play_idx, play in enumerate(all_plays):
            # Look for the correct UUID playId - might be nested differently
            play_id = play.get('playId')
            uuid_play_id = play.get('playGuid') or play.get('uuid') or play.get('guid')
            play_events = play.get('playEvents', [])
            play_about = play.get('about', {})
            play_inning = play_about.get('inning')
            
            logger.debug(f"Play {play_idx}: playId={play_id}, uuidPlayId={uuid_play_id}, inning={play_inning}")
            
            # If we find events, also log their structure for debugging
            if play_idx < 3 and len(play_events) > 0:  # Log first few plays for debugging
                logger.debug(f"Play {play_idx} structure: {list(play.keys())}")
                if play_events:
                    logger.debug(f"First event structure: {list(play_events[0].keys())}")
            
            # Only check plays from the target inning for efficiency
            if play_inning == inning:
                logger.debug(f"Checking play {play_idx} in inning {play_inning} with {len(play_events)} events")
                
                for event_idx, event in enumerate(play_events):
                    # Check if this event matches our criteria
                    event_pitch_number = event.get('pitchNumber')
                    
                    logger.debug(f"Event {event_idx}: play_inning={play_inning}, pitchNumber={event_pitch_number}")
                    
                    # Match based on play inning and event pitch number
                    if play_inning == inning and event_pitch_number == pitch_number:
                        # Optional: verify it's a swinging strike
                        description = event.get('details', {}).get('description', '')
                        
                        # Look for the correct UUID playId in various possible locations
                        uuid_play_id = (
                            play.get('playId') or 
                            event.get('playId') or
                            event.get('uuid') or
                            event.get('guid') or
                            event.get('playGuid') or
                            play.get('about', {}).get('playId') or
                            event.get('about', {}).get('playId')
                        )
                        
                        logger.info(f"Found matching pitch: numericId={play_id}, uuidPlayId={uuid_play_id}, description={description}")
                        logger.debug(f"Event keys for debugging: {list(event.keys())}")
                        
                        # Use the UUID if found, otherwise fall back to numeric
                        final_play_id = uuid_play_id if uuid_play_id else play_id
                        
                        # Get the best available video URL and type
                        video_info = get_best_video_url(final_play_id)
                        
                        response_data = {
                            "success": True,
                            "playId": final_play_id,
                            "numeric_id": play_id,
                            "uuid_id": uuid_play_id,
                            "description": description,
                            "game_pk": game_pk,
                            "inning": inning,
                            "pitch_number": pitch_number
                        }
                        
                        if video_info:
                            response_data.update({
                                "video_type": video_info["video_type"],
                                "video_url": video_info["video_url"]
                            })
                            
                            # Extract the direct MP4 download URL
                            download_url = get_video_url_from_sporty_page(final_play_id)
                            response_data["download_url"] = download_url
                        else:
                            # Try without video type as fallback
                            fallback_url = f"https://baseballsavant.mlb.com/sporty-videos?playId={final_play_id}"
                            download_url = get_video_url_from_sporty_page(final_play_id)
                            
                            response_data.update({
                                "video_type": None,
                                "video_url": fallback_url,
                                "download_url": download_url,
                                "note": "Using fallback video URL"
                            })
                        
                        return jsonify(response_data)
        
        # No matching pitch found
        logger.warning(f"No matching pitch found for game {game_pk}, inning {inning}, pitch {pitch_number}")
        return jsonify({
            "success": False,
            "error": f"No pitch found for game {game_pk}, inning {inning}, pitch number {pitch_number}"
        }), 404
        
    except Exception as e:
        logger.error(f"Error in get_play_id: {str(e)}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "SwordFinder API",
        "version": "1.0.0"
    })

@app.route('/download-videos/<date>', methods=['POST'])
def download_videos_for_date(date):
    """
    Download videos for sword swings on a specific date
    Used to pre-download videos if needed
    """
    try:
        # Get sword swings for the date
        result = db_sword_finder.find_sword_swings(date)
        sword_swings = result.get('data', [])[:5]  # Top 5 only
        
        download_results = {
            "date": date,
            "processed": 0,
            "downloaded": 0,
            "failed": 0,
            "videos": []
        }
        
        for sword in sword_swings:
            play_id = sword.get('play_id')
            download_results["processed"] += 1
            
            if play_id:
                try:
                    # Get and download the video
                    download_url = get_video_url_from_sporty_page(play_id)
                    if download_url:
                        result = download_sword_clip(play_id, download_url)
                        if result:
                            download_results["downloaded"] += 1
                            download_results["videos"].append({
                                "play_id": play_id,
                                "player": sword.get('player_name'),
                                "path": result['path'],
                                "size": result['file_size']
                            })
                        else:
                            download_results["failed"] += 1
                    else:
                        download_results["failed"] += 1
                except Exception as e:
                    download_results["failed"] += 1
                    logger.error(f"Error downloading video {play_id}: {str(e)}")
        
        return jsonify({
            "success": True,
            "results": download_results
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/video-stats', methods=['GET'])
def video_stats():
    """Get statistics about downloaded videos"""
    try:
        stats = get_download_stats()
        
        # Add directory info
        video_dir = "static/videos"
        if os.path.exists(video_dir):
            video_files = [f for f in os.listdir(video_dir) if f.endswith('.mp4')]
            stats["video_files_on_disk"] = len(video_files)
        else:
            stats["video_files_on_disk"] = 0
            
        return jsonify({
            "success": True,
            "stats": stats
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/top-swords-2025', methods=['GET'])
def get_top_swords_for_2025():
    """
    API endpoint to get the top 5 sword swings for the year 2025,
    ordered by raw_sword_metric.
    """
    logger.info("Fetching top 5 swords for 2025")
    top_swords_list = []
    try:
        with get_db() as db_session:
            # Query to get top 5 swords for 2025 by raw_sword_metric
            # Ensure game_date is treated as string for comparison if it's VARCHAR
            query = text("""
                SELECT 
                    ss.id as sword_swing_id,
                    ss.raw_sword_metric, 
                    ss.sword_score, 
                    ss.video_url, 
                    ss.local_mp4_path, 
                    ss.mp4_downloaded,
                    sp.game_date, 
                    sp.player_name as pitcher_name, 
                    sp.batter as batter_id, 
                    sp.pitch_type, 
                    sp.pitch_name as descriptive_pitch_name, 
                    sp.release_speed,
                    sp.inning, 
                    sp.inning_topbot, 
                    sp.home_team, 
                    sp.away_team,
                    sp.description as pitch_description,
                    ss.pitch_id as statcast_pitch_db_id
                FROM sword_swings ss
                JOIN statcast_pitches sp ON ss.pitch_id = sp.id
                WHERE (sp.game_date LIKE '2025-%' OR (sp.game_date >= '2025-01-01' AND sp.game_date <= '2025-12-31'))
                  AND ss.raw_sword_metric IS NOT NULL
                ORDER BY ss.raw_sword_metric DESC
                LIMIT 5
            """)
            
            result = db_session.execute(query)
            raw_top_swords = result.mappings().all() # Get results as list of dict-like objects

            for sword_data_db in raw_top_swords:
                item = dict(sword_data_db) # Convert to mutable dict

                # Fetch Batter Name
                batter_mlbam_id = item.get('batter_id')
                batter_name_str = f"Batter ID: {batter_mlbam_id}" 
                if batter_mlbam_id:
                    try:
                        api_url = f"https://statsapi.mlb.com/api/v1/people/{batter_mlbam_id}"
                        response = requests.get(api_url, timeout=5)
                        response.raise_for_status()
                        batter_api_data = response.json()
                        if batter_api_data.get("people") and len(batter_api_data["people"]) > 0:
                            batter_name_str = batter_api_data["people"][0].get("fullName", batter_name_str)
                    except requests.exceptions.RequestException as e_batter:
                        logger.warning(f"Could not fetch batter name for ID {batter_mlbam_id}: {e_batter}")
                    except ValueError: 
                        logger.warning(f"Could not parse JSON for batter ID {batter_mlbam_id}")
                item['batter_name'] = batter_name_str

                # Adjust local_mp4_path to be web-accessible
                if item.get('local_mp4_path'):
                    item['local_mp4_path'] = item['local_mp4_path'].lstrip('/')
                
                top_swords_list.append(item)
        
        return jsonify({"success": True, "data": top_swords_list, "count": len(top_swords_list)})

    except Exception as e:
        logger.error(f"Error in /api/top-swords-2025: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500

@app.route('/patch-monitor', methods=['GET'])
def patch_monitor():
    """Database patch control center - integrated version"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🗡️ Database Patch Control</title>
        <meta http-equiv="refresh" content="3">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #1a1a1a; color: #fff; }
            .container { max-width: 800px; margin: 0 auto; }
            .status-card { background: #2d2d2d; padding: 20px; border-radius: 10px; margin: 20px 0; }
            .status-running { border-left: 5px solid #4CAF50; }
            .status-idle { border-left: 5px solid #FFC107; }
            .status-error { border-left: 5px solid #F44336; }
            .status-completed { border-left: 5px solid #2196F3; }
            .progress-bar { background: #444; height: 20px; border-radius: 10px; overflow: hidden; }
            .progress-fill { background: #4CAF50; height: 100%; transition: width 0.3s; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
            .stat { background: #333; padding: 15px; border-radius: 8px; text-align: center; }
            .stat-value { font-size: 2em; font-weight: bold; color: #4CAF50; }
            .button { background: #4CAF50; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            .button:disabled { background: #666; cursor: not-allowed; }
            .log { background: #1e1e1e; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 14px; max-height: 300px; overflow-y: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🗡️ SwordFinder Database Patch Monitor</h1>
            
            <div class="status-card status-{{ status.status.lower() }}">
                <h2>Status: {{ status.status }}</h2>
                <p><strong>Current Task:</strong> {{ status.current_processing or "Ready to patch database" }}</p>
                <p><strong>Elapsed Time:</strong> {{ status.elapsed_time }}s</p>
                
                {% if status.total_expected > 0 %}
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {{ (status.rows_scanned / status.total_expected * 100) if status.total_expected > 0 else 0 }}%"></div>
                </div>
                <p>{{ status.rows_scanned }} / {{ status.total_expected }} rows processed</p>
                {% endif %}
            </div>

            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{{ status.rows_scanned }}</div>
                    <div>Rows Scanned</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ status.rows_updated }}</div>
                    <div>Rows Updated</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ "%.1f"|format(status.rows_updated / status.rows_scanned * 100) if status.rows_scanned > 0 else 0 }}%</div>
                    <div>Update Rate</div>
                </div>
            </div>

            <div style="margin: 30px 0;">
                <form action="/start-patch" method="post" style="display: inline;">
                    <button type="submit" class="button" {{ "disabled" if status.status == "Running" else "" }}>
                        Start Database Patch
                    </button>
                </form>
            </div>

            {% if status.error_message %}
            <div class="status-card status-error">
                <h3>Error Details</h3>
                <div class="log">{{ status.error_message }}</div>
            </div>
            {% endif %}

            <div class="status-card">
                <h3>Process Information</h3>
                <div class="log">
                    <div>Missing Data to Fix:</div>
                    <div>• Team names: 0 records have team data (need BOS, BAL, etc.)</div>
                    <div>• Velocities: Limited records have pitch speed data</div>
                    <div>• Spin rates: 0 records have spin rate data</div>
                    <div>• Locations: Limited plate position data</div>
                    <div><br>Patch will pull fresh pybaseball data and update missing fields.</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, status=patch_status, now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/csv-patch-monitor')
def csv_patch_monitor():
    """CSV patch monitoring interface"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🗡️ CSV Database Patch Monitor</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #1a1a1a; color: #fff; }
            .container { max-width: 900px; margin: 0 auto; }
            .status-card { background: #2d2d2d; padding: 25px; border-radius: 12px; margin: 20px 0; }
            .status-running { border-left: 6px solid #4CAF50; }
            .status-ready { border-left: 6px solid #FFC107; }
            .status-error { border-left: 6px solid #F44336; }
            .status-completed { border-left: 6px solid #2196F3; }
            .progress-bar { background: #444; height: 25px; border-radius: 12px; overflow: hidden; margin: 15px 0; }
            .progress-fill { background: linear-gradient(90deg, #4CAF50, #45a049); height: 100%; transition: width 0.5s; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin: 25px 0; }
            .stat { background: #333; padding: 20px; border-radius: 10px; text-align: center; }
            .stat-value { font-size: 2.2em; font-weight: bold; color: #4CAF50; margin-bottom: 8px; }
            .stat-label { color: #bbb; font-size: 0.9em; }
            .button { background: #4CAF50; color: white; padding: 15px 30px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; margin: 10px; }
            .button:disabled { background: #666; cursor: not-allowed; }
            h1 { text-align: center; color: #4CAF50; margin-bottom: 30px; }
            .eta { background: #444; padding: 15px; border-radius: 8px; margin: 15px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🗡️ CSV Database Patch Monitor</h1>
            
            <div class="status-card status-ready">
                <h2>Ready to Patch Database from CSV</h2>
                <p><strong>Source:</strong> complete_statcast_2025.csv (226,833 records)</p>
                <p><strong>Target:</strong> PostgreSQL statcast_pitches table</p>
                <p><strong>Action:</strong> Update missing team names, spin rates, and other fields</p>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <button class="button" onclick="startCSVPatch()">
                    Start CSV Patch
                </button>
            </div>
        </div>
        
        <script>
            function startCSVPatch() {
                if (confirm('Start CSV patch to update all missing database fields from your complete CSV file?')) {
                    fetch('/start-csv-patch', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.href = '/csv-patch-status';
                        } else {
                            alert('Error: ' + data.error);
                        }
                    });
                }
            }
        </script>
        </div>
    </body>
    </html>
    """)

@app.route('/start-csv-patch', methods=['POST'])
def start_csv_patch():
    """Start the CSV patch process"""
    global patch_status
    
    if patch_status["status"] == "Running":
        return jsonify({"success": False, "error": "Patch already running"})
    
    # Reset status for CSV patch
    patch_status.update({
        "status": "Running",
        "rows_scanned": 0,
        "rows_updated": 0,
        "current_processing": "Loading CSV file...",
        "start_time": time_module.time(),
        "error_message": ""
    })
    
    # Start CSV patch in background
    thread = threading.Thread(target=run_csv_patch_process)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True})

@app.route('/database-status')
def database_status():
    """Check actual database completion status"""
    try:
        from models import get_db
        
        with get_db() as db:
            # Get completion status by date
            result = db.execute("""
                SELECT game_date, 
                       COUNT(*) as total_pitches,
                       COUNT(home_team) as has_teams,
                       COUNT(release_spin_rate) as has_spin_rates,
                       ROUND(COUNT(home_team) * 100.0 / COUNT(*), 1) as completion_pct
                FROM statcast_pitches 
                GROUP BY game_date
                ORDER BY game_date
            """).fetchall()
            
            dates_data = []
            for row in result:
                dates_data.append({
                    'date': row[0],
                    'total': row[1], 
                    'teams': row[2],
                    'spin_rates': row[3],
                    'completion': row[4]
                })
            
            return jsonify({
                'success': True,
                'dates': dates_data,
                'summary': {
                    'total_dates': len(dates_data),
                    'completed_dates': len([d for d in dates_data if d['completion'] == 100.0]),
                    'march_30_status': next((d for d in dates_data if d['date'] == '2025-03-30'), None)
                }
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/csv-patch-status')
def csv_patch_status():
    """Live CSV patch status monitoring"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🗡️ CSV Patch Status</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #1a1a1a; color: #fff; }
            .container { max-width: 900px; margin: 0 auto; }
            .status-card { background: #2d2d2d; padding: 25px; border-radius: 12px; margin: 20px 0; }
            .status-running { border-left: 6px solid #4CAF50; }
            .status-completed { border-left: 6px solid #2196F3; }
            .status-error { border-left: 6px solid #F44336; }
            .progress-bar { background: #444; height: 25px; border-radius: 12px; overflow: hidden; margin: 15px 0; }
            .progress-fill { background: linear-gradient(90deg, #4CAF50, #45a049); height: 100%; transition: width 0.5s; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 18px; margin: 25px 0; }
            .stat { background: #333; padding: 20px; border-radius: 10px; text-align: center; }
            .stat-value { font-size: 2.2em; font-weight: bold; color: #4CAF50; margin-bottom: 8px; }
            .stat-label { color: #bbb; font-size: 0.9em; }
            h1 { text-align: center; color: #4CAF50; margin-bottom: 30px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🗡️ CSV Patch Status</h1>
            
            <div class="status-card status-{{ status.status.lower() }}">
                <h2>Status: {{ status.status }}</h2>
                <p><strong>Current Task:</strong> {{ status.current_processing }}</p>
                <p><strong>Elapsed Time:</strong> {{ "%.1f"|format(status.elapsed_time) }}s</p>
                {% if status.error_message %}
                    <p style="color: #F44336;"><strong>Error:</strong> {{ status.error_message }}</p>
                {% endif %}
            </div>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{{ "{:,}"|format(status.rows_scanned) }}</div>
                    <div class="stat-label">Rows Processed</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ "{:,}"|format(status.rows_updated) }}</div>
                    <div class="stat-label">Records Updated</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ "%.1f"|format((status.rows_scanned / status.elapsed_time) if status.elapsed_time > 0 else 0) }}</div>
                    <div class="stat-label">Records/sec</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, status=patch_status, now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/start-patch', methods=['POST'])
def start_patch():
    """Start the database patching process"""
    global patch_status
    
    if patch_status["status"] == "Running":
        return jsonify({"success": False, "error": "Patch already running"}), 400
    
    # Reset status
    patch_status.update({
        "status": "Running",
        "rows_scanned": 0,
        "rows_updated": 0,
        "current_processing": "Initializing...",
        "start_time": time_module.time(),
        "error_message": ""
    })
    
    # Start patch in background thread
    thread = threading.Thread(target=run_patch_process)
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('patch_monitor'))

def run_patch_process():
    """Main patching process - runs in background"""
    global patch_status
    
    try:
        database_url = os.environ.get('DATABASE_URL')
        engine = create_engine(database_url)
        
        # Define date range to patch (recent dates first)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)  # Last 7 days
        
        patch_status["current_processing"] = f"Pulling Statcast data from {start_date} to {end_date}"
        logger.info(f"Starting patch: pulling data from {start_date} to {end_date}")
        
        # Pull fresh data from pybaseball
        df = statcast(start_dt=str(start_date), end_dt=str(end_date))
        patch_status["total_expected"] = len(df)
        logger.info(f"Retrieved {len(df)} records from pybaseball")
        
        with engine.connect() as conn:
            batch_size = 500
            updated_count = 0
            
            for i in range(0, len(df), batch_size):
                if patch_status["status"] != "Running":  # Allow stopping
                    break
                    
                batch = df.iloc[i:i+batch_size]
                patch_status["current_processing"] = f"Processing batch {i//batch_size + 1} (rows {i}-{min(i+batch_size, len(df))})"
                
                for idx, row in batch.iterrows():
                    patch_status["rows_scanned"] = idx + 1
                    
                    # Build update query for missing fields
                    update_fields = []
                    params = {
                        'game_pk': int(row['game_pk']) if pd.notna(row['game_pk']) else None,
                        'player_name': str(row['player_name']) if pd.notna(row['player_name']) else None,
                        'pitch_type': str(row['pitch_type']) if pd.notna(row['pitch_type']) else None
                    }
                    
                    # Add fields that might be missing
                    if pd.notna(row['release_speed']):
                        update_fields.append("release_speed = COALESCE(release_speed, :release_speed)")
                        params['release_speed'] = float(row['release_speed'])
                    
                    if pd.notna(row['home_team']):
                        update_fields.append("home_team = COALESCE(home_team, :home_team)")
                        params['home_team'] = str(row['home_team'])
                    
                    if pd.notna(row['away_team']):
                        update_fields.append("away_team = COALESCE(away_team, :away_team)")
                        params['away_team'] = str(row['away_team'])
                    
                    if pd.notna(row['release_spin_rate']):
                        update_fields.append("release_spin_rate = COALESCE(release_spin_rate, :release_spin_rate)")
                        params['release_spin_rate'] = float(row['release_spin_rate'])
                    
                    if pd.notna(row['plate_x']):
                        update_fields.append("plate_x = COALESCE(plate_x, :plate_x)")
                        params['plate_x'] = float(row['plate_x'])
                    
                    if pd.notna(row['plate_z']):
                        update_fields.append("plate_z = COALESCE(plate_z, :plate_z)")
                        params['plate_z'] = float(row['plate_z'])
                    
                    if pd.notna(row['pitch_name']):
                        update_fields.append("pitch_name = COALESCE(pitch_name, :pitch_name)")
                        params['pitch_name'] = str(row['pitch_name'])
                    
                    # Only update if we have fields and valid keys
                    if update_fields and all(params[k] is not None for k in ['game_pk', 'player_name', 'pitch_type']):
                        update_query = text(f"""
                            UPDATE statcast_pitches 
                            SET {', '.join(update_fields)}
                            WHERE game_pk = :game_pk
                            AND player_name = :player_name
                            AND pitch_type = :pitch_type
                        """)
                        
                        result = conn.execute(update_query, params)
                        if result.rowcount > 0:
                            updated_count += result.rowcount
                            patch_status["rows_updated"] = updated_count
                
                # Commit after each batch
                conn.commit()
                logger.info(f"Batch {i//batch_size + 1} complete. Updated {updated_count} records so far.")
        
        patch_status["status"] = "Completed"
        patch_status["current_processing"] = f"Patch completed! Updated {updated_count} records"
        logger.info(f"Patch process completed successfully. Updated {updated_count} total records.")
        
    except Exception as e:
        patch_status["status"] = "Error"
        patch_status["error_message"] = str(e)
        patch_status["current_processing"] = "Error occurred during patching"
        logger.error(f"Patch process failed: {e}")
        logger.error(traceback.format_exc())

def run_csv_patch_process():
    """CSV patch process with real-time monitoring"""
    global patch_status
    
    try:
        import psycopg2
        
        # Connect to database
        database_url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        patch_status["current_processing"] = "Loading CSV file..."
        
        # Load CSV with all authentic MLB data
        df = pd.read_csv('complete_statcast_2025.csv', low_memory=False)
        patch_status["current_processing"] = f"Processing {len(df)} records from CSV..."
        
        # Prepare efficient update query
        update_query = """
        UPDATE statcast_pitches 
        SET 
            home_team = COALESCE(home_team, %s),
            away_team = COALESCE(away_team, %s),
            release_speed = COALESCE(release_speed, %s),
            release_spin_rate = COALESCE(release_spin_rate, %s),
            spin_axis = COALESCE(spin_axis, %s),
            plate_x = COALESCE(plate_x, %s),
            plate_z = COALESCE(plate_z, %s),
            pitch_name = COALESCE(pitch_name, %s),
            stand = COALESCE(stand, %s),
            p_throws = COALESCE(p_throws, %s),
            sz_top = COALESCE(sz_top, %s),
            sz_bot = COALESCE(sz_bot, %s)
        WHERE game_pk = %s 
        AND game_date = %s
        AND pitcher = %s
        AND batter = %s
        """
        
        batch_size = 1000
        
        for i in range(0, len(df), batch_size):
            if patch_status["status"] != "Running":
                break
                
            batch = df.iloc[i:i+batch_size]
            batch_data = []
            
            for _, row in batch.iterrows():
                # Skip if missing critical fields
                if pd.isna(row.get('game_pk')) or pd.isna(row.get('game_date')):
                    continue
                    
                def safe_value(val):
                    return None if pd.isna(val) or val == '' else val
                
                update_data = (
                    safe_value(row.get('home_team')),
                    safe_value(row.get('away_team')),
                    safe_value(row.get('release_speed')),
                    safe_value(row.get('release_spin_rate')),
                    safe_value(row.get('spin_axis')),
                    safe_value(row.get('plate_x')),
                    safe_value(row.get('plate_z')),
                    safe_value(row.get('pitch_name')),
                    safe_value(row.get('stand')),
                    safe_value(row.get('p_throws')),
                    safe_value(row.get('sz_top')),
                    safe_value(row.get('sz_bot')),
                    # WHERE conditions
                    int(row.get('game_pk')) if not pd.isna(row.get('game_pk')) else None,
                    str(row.get('game_date')) if not pd.isna(row.get('game_date')) else None,
                    int(row.get('pitcher')) if not pd.isna(row.get('pitcher')) else None,
                    int(row.get('batter')) if not pd.isna(row.get('batter')) else None
                )
                batch_data.append(update_data)
            
            # Execute batch update
            if batch_data:
                cursor.executemany(update_query, batch_data)
                patch_status["rows_updated"] += cursor.rowcount
                conn.commit()
            
            # Update monitoring status
            patch_status["rows_scanned"] = min(i + batch_size, len(df))
            patch_status["elapsed_time"] = time_module.time() - patch_status["start_time"]
            patch_status["current_processing"] = f"Batch {i//batch_size + 1}: Updated {patch_status['rows_updated']} records"
        
        cursor.close()
        conn.close()
        
        patch_status["status"] = "Completed"
        patch_status["current_processing"] = f"CSV patch completed! Updated {patch_status['rows_updated']} records with authentic MLB data"
        
    except Exception as e:
        patch_status["status"] = "Error"
        patch_status["error_message"] = str(e)
        patch_status["current_processing"] = f"Error: {str(e)}"

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "error": "Method not allowed"
    }), 405

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
