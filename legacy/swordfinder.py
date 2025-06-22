import logging
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import traceback
from percentile_analyzer import PercentileAnalyzer
import os

logger = logging.getLogger(__name__)

class SwordFinder:
    """
    Core logic for identifying and scoring sword swings from Statcast data
    """
    
    def __init__(self):
        self.weight_bat_speed = 0.35
        self.weight_swing_tilt = 0.25
        self.weight_intercept_y = 0.25
        self.weight_zone_penalty = 0.15
        
        # Initialize percentile analyzer
        try:
            self.percentile_analyzer = PercentileAnalyzer()
            logger.info("Percentile analyzer loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load percentile analyzer: {e}")
            self.percentile_analyzer = None
        
    def find_sword_swings(self, date_str):
        """
        Main method to find and score sword swings for a given date
        
        Args:
            date_str (str): Date in YYYY-MM-DD format
            
        Returns:
            list: Top 5 sword swings with scores
        """
        try:
            # Import pybaseball here to handle potential import issues
            try:
                from pybaseball import statcast
            except ImportError as e:
                logger.error(f"Failed to import pybaseball: {e}")
                raise Exception("pybaseball library not available. Please install it.")
            
            logger.info(f"Fetching Statcast data for {date_str}")
            
            # Fetch Statcast data for the given date
            try:
                data = statcast(start_dt=date_str, end_dt=date_str)
            except Exception as e:
                logger.error(f"Failed to fetch Statcast data: {e}")
                raise Exception(f"Failed to fetch Statcast data: {str(e)}")
            
            if data is None or len(data) == 0:
                logger.warning(f"No Statcast data found for {date_str}")
                return []
            
            logger.info(f"Retrieved {len(data)} total pitches from Statcast")
            
            # Apply sword swing filters
            sword_candidates = self._apply_sword_filters(data)
            
            if len(sword_candidates) == 0:
                logger.info("No sword swings found matching criteria")
                return []
            
            logger.info(f"Found {len(sword_candidates)} sword swing candidates")
            
            # Calculate sword scores
            scored_swings = self._calculate_sword_scores(sword_candidates)
            
            # Return top 5 sword swings
            top_swings = scored_swings.head(5)
            
            # Fetch playIds for each sword swing
            results_with_playids = self._add_play_ids(top_swings)
            
            return self._format_results(results_with_playids)
            
        except Exception as e:
            logger.error(f"Error in find_sword_swings: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _apply_sword_filters(self, data):
        """
        Apply filtering criteria to identify sword swing candidates
        
        Criteria:
        - swinging_strike or swinging_strike_blocked
        - bat_speed < 60
        - intercept_ball_minus_batter_pos_y_inches > 14
        - swing_path_tilt > 30
        """
        logger.info("Applying sword swing filters")
        
        # Create a copy to avoid modifying original data
        filtered_data = data.copy()
        
        # Filter 1: Swing outcome (swinging_strike or swinging_strike_blocked)
        swing_outcomes = ['swinging_strike', 'swinging_strike_blocked']
        filtered_data = filtered_data[filtered_data['description'].isin(swing_outcomes)]
        logger.info(f"After swing outcome filter: {len(filtered_data)} swings")
        
        if len(filtered_data) == 0:
            return pd.DataFrame()
        
        # Filter 2: Bat speed < 60 mph
        # Handle missing bat_speed values
        filtered_data = filtered_data.dropna(subset=['bat_speed'])
        filtered_data = filtered_data[filtered_data['bat_speed'] < 60]
        logger.info(f"After bat speed filter: {len(filtered_data)} swings")
        
        if len(filtered_data) == 0:
            return pd.DataFrame()
        
        # Filter 3: Intercept Y > 14 inches
        # Handle missing intercept values
        intercept_col = 'intercept_ball_minus_batter_pos_y_inches'
        if intercept_col in filtered_data.columns:
            filtered_data = filtered_data.dropna(subset=[intercept_col])
            filtered_data = filtered_data[filtered_data[intercept_col] > 14]
            logger.info(f"After intercept Y filter: {len(filtered_data)} swings")
        else:
            logger.warning(f"Column {intercept_col} not found in data")
            return pd.DataFrame()
        
        if len(filtered_data) == 0:
            return pd.DataFrame()
        
        # Filter 4: Swing path tilt > 30 degrees
        if 'swing_path_tilt' in filtered_data.columns:
            filtered_data = filtered_data.dropna(subset=['swing_path_tilt'])
            filtered_data = filtered_data[filtered_data['swing_path_tilt'] > 30]
            logger.info(f"After swing path tilt filter: {len(filtered_data)} swings")
        else:
            logger.warning("Column 'swing_path_tilt' not found in data")
            return pd.DataFrame()
        
        return filtered_data
    
    def _calculate_sword_scores(self, data):
        """
        Calculate weighted sword scores for each swing
        
        Formula:
        sword_score = (
            0.35 * (60 - bat_speed)/60 +
            0.25 * swing_path_tilt/60 +
            0.25 * intercept_y/50 +
            0.15 * zone_penalty
        )
        """
        logger.info("Calculating sword scores")
        
        scored_data = data.copy()
        
        # Calculate individual components
        bat_speed_component = self.weight_bat_speed * (60 - scored_data['bat_speed']) / 60
        tilt_component = self.weight_swing_tilt * scored_data['swing_path_tilt'] / 60
        intercept_component = self.weight_intercept_y * scored_data['intercept_ball_minus_batter_pos_y_inches'] / 50
        
        # Calculate zone penalty (higher penalty for strikes in zone)
        zone_penalty = self._calculate_zone_penalty(scored_data)
        zone_component = self.weight_zone_penalty * zone_penalty
        
        # Calculate raw sword score
        raw_score = bat_speed_component + tilt_component + intercept_component + zone_component
        
        # Normalize to 50-100 scale
        min_score = raw_score.min()
        max_score = raw_score.max()
        
        if max_score == min_score:
            normalized_score = pd.Series([75.0] * len(raw_score), index=raw_score.index)
        else:
            normalized_score = 50 + (raw_score - min_score) / (max_score - min_score) * 50
        
        scored_data['sword_score'] = normalized_score
        
        # Sort by sword score descending
        scored_data = scored_data.sort_values('sword_score', ascending=False)
        
        return scored_data
    
    def _calculate_zone_penalty(self, data):
        """
        Calculate zone penalty based on strike zone location
        Higher penalty for pitches in the strike zone (easier to hit)
        """
        if 'zone' in data.columns:
            # Zone 1-9 are in strike zone, zone 11-14 are outside
            zone_penalty = np.where(data['zone'].between(1, 9), 0.3, 0.7)
        else:
            # Default penalty if zone data not available
            zone_penalty = np.full(len(data), 0.5)
        
        return pd.Series(zone_penalty, index=data.index)
    
    def _add_play_ids(self, data):
        """
        Fetch playIds for each sword swing using MLB Stats API
        """
        logger.info("Fetching playIds for sword swings")
        
        # Create a copy to avoid modifying original data
        data_with_playids = data.copy()
        
        # Group by game_pk to minimize API calls
        unique_games = data['game_pk'].unique()
        
        for game_pk in unique_games:
            try:
                # Fetch game data from MLB Stats API
                mlb_api_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
                response = requests.get(mlb_api_url, timeout=10)
                response.raise_for_status()
                game_data = response.json()
                
                # Parse plays data
                all_plays = game_data['liveData']['plays']['allPlays']
                
                # For each sword swing in this game, find its playId
                game_swings = data[data['game_pk'] == game_pk]
                
                for idx, swing in game_swings.iterrows():
                    inning = swing['inning']
                    pitch_number = swing['pitch_number']
                    at_bat_number = swing.get('at_bat_number')
                    batter_id = swing.get('batter')
                    
                    # Search for matching pitch in game data with more specific criteria
                    play_id = self._find_play_id_for_pitch(all_plays, inning, pitch_number, at_bat_number, batter_id)
                    
                    if play_id:
                        data_with_playids.loc[idx, 'play_id'] = play_id
                        logger.debug(f"Found playId {play_id} for game {game_pk}, inning {inning}, pitch {pitch_number}, at-bat {at_bat_number}")
                    else:
                        logger.warning(f"No playId found for game {game_pk}, inning {inning}, pitch {pitch_number}, at-bat {at_bat_number}")
                        
            except Exception as e:
                logger.warning(f"Failed to fetch playIds for game {game_pk}: {str(e)}")
                continue
        
        # Add batter names
        data_with_names = self._add_batter_names(data_with_playids)
        
        return data_with_names
    
    def _find_play_id_for_pitch(self, all_plays, target_inning, target_pitch_number, target_at_bat_number=None, target_batter_id=None):
        """
        Find the playId for a specific pitch within game play data
        Uses multiple criteria for precise matching
        """
        for play in all_plays:
            play_about = play.get('about', {})
            play_inning = play_about.get('inning')
            
            # Only check plays from the target inning
            if play_inning == target_inning:
                # If we have at-bat number, use it for additional matching
                if target_at_bat_number:
                    play_at_bat_index = play_about.get('atBatIndex')
                    if play_at_bat_index is not None and (play_at_bat_index + 1) != target_at_bat_number:
                        continue
                
                # If we have batter ID, check if it matches
                if target_batter_id:
                    matchup = play.get('matchup', {})
                    batter_info = matchup.get('batter', {})
                    if batter_info.get('id') != target_batter_id:
                        continue
                
                play_events = play.get('playEvents', [])
                
                for event in play_events:
                    event_pitch_number = event.get('pitchNumber')
                    
                    if event_pitch_number == target_pitch_number:
                        # Look for UUID playId in the event
                        uuid_play_id = (
                            event.get('playId') or
                            event.get('uuid') or
                            event.get('guid') or
                            event.get('playGuid')
                        )
                        
                        if uuid_play_id:
                            return str(uuid_play_id)
        
        return None
    
    def _add_batter_names(self, data):
        """
        Add batter names by looking up batter IDs via MLB Stats API
        """
        if data.empty:
            return data
        
        # Get unique batter IDs
        unique_batter_ids = data['batter'].dropna().unique()
        batter_name_cache = {}
        
        # Fetch batter names from MLB Stats API
        for batter_id in unique_batter_ids:
            try:
                batter_id = int(batter_id)
                url = f"https://statsapi.mlb.com/api/v1/people/{batter_id}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    player_data = response.json()
                    people = player_data.get('people', [])
                    if people:
                        full_name = people[0].get('fullName', 'Unknown Batter')
                        batter_name_cache[batter_id] = full_name
                        logger.debug(f"Found batter name: {full_name} for ID {batter_id}")
                    else:
                        batter_name_cache[batter_id] = 'Unknown Batter'
                else:
                    logger.warning(f"Failed to fetch batter info for ID {batter_id}: {response.status_code}")
                    batter_name_cache[batter_id] = 'Unknown Batter'
                    
            except Exception as e:
                logger.warning(f"Error fetching batter name for ID {batter_id}: {str(e)}")
                batter_name_cache[batter_id] = 'Unknown Batter'
        
        # Add batter names to dataframe
        data_copy = data.copy()
        data_copy['batter_name'] = data_copy['batter'].map(lambda x: batter_name_cache.get(int(x) if pd.notna(x) else None, 'Unknown Batter'))
        
        return data_copy
    
    def _format_results(self, data):
        """
        Format the results for JSON response
        """
        results = []
        
        for _, row in data.iterrows():
            play_id = self._safe_get(row, 'play_id', '')
            video_url = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}" if play_id else ""
            
            # Get direct MP4 download URL
            download_url = self._get_mp4_download_url(play_id) if play_id else None
            
            result = {
                "play_id": play_id,
                "game_pk": int(row['game_pk']) if pd.notna(row.get('game_pk')) else None,
                "player_name": self._safe_get(row, 'player_name', 'Unknown Player'),
                "pitcher_name": self._safe_get(row, 'player_name', 'Unknown Pitcher'),
                "batter_name": self._safe_get(row, 'batter_name', 'Unknown Batter'),
                "pitch_type": self._safe_get(row, 'pitch_type', 'Unknown'),
                "pitch_name": self._get_pitch_name(self._safe_get(row, 'pitch_type', 'Unknown')),
                "release_speed": round(float(row['release_speed']), 1) if pd.notna(row.get('release_speed')) else None,
                "release_spin_rate": int(row['release_spin_rate']) if pd.notna(row.get('release_spin_rate')) else None,
                "plate_x": round(float(row['plate_x']), 2) if pd.notna(row.get('plate_x')) else None,
                "plate_z": round(float(row['plate_z']), 2) if pd.notna(row.get('plate_z')) else None,
                "sz_top": round(float(row['sz_top']), 2) if pd.notna(row.get('sz_top')) else None,
                "sz_bot": round(float(row['sz_bot']), 2) if pd.notna(row.get('sz_bot')) else None,
                "bat_speed": round(float(row['bat_speed']), 1),
                "swing_path_tilt": round(float(row['swing_path_tilt']), 1),
                "attack_angle": round(float(row['attack_angle']), 1) if pd.notna(row.get('attack_angle')) else None,
                "intercept_ball_minus_batter_pos_y_inches": round(float(row['intercept_ball_minus_batter_pos_y_inches']), 1),
                "description": self._safe_get(row, 'description', 'Unknown'),
                "events": self._safe_get(row, 'events', 'Unknown'),
                "inning": int(row['inning']) if pd.notna(row.get('inning')) else None,
                "balls": int(row['balls']) if pd.notna(row.get('balls')) else None,
                "strikes": int(row['strikes']) if pd.notna(row.get('strikes')) else None,
                "at_bat_number": int(row['at_bat_number']) if pd.notna(row.get('at_bat_number')) else None,
                "pitch_number": int(row['pitch_number']) if pd.notna(row.get('pitch_number')) else None,
                "home_team": self._safe_get(row, 'home_team', 'Unknown'),
                "away_team": self._safe_get(row, 'away_team', 'Unknown'),
                "batter": int(row['batter']) if pd.notna(row.get('batter')) else None,
                "pitcher": int(row['pitcher']) if pd.notna(row.get('pitcher')) else None,
                "video_url": video_url,
                "download_url": download_url,
                "sword_score": round(float(row['sword_score']), 1)
            }
            
            # Add percentile analysis if available
            if self.percentile_analyzer:
                try:
                    # Create pitch data dictionary for analysis
                    pitch_data = {
                        'pitch_type': result['pitch_type'],
                        'pitch_name': result['pitch_name'],
                        'release_speed': result['release_speed'],
                        'release_spin_rate': result['release_spin_rate'],
                        'pfx_x': round(float(row['pfx_x']), 2) if pd.notna(row.get('pfx_x')) else None,
                        'pfx_z': round(float(row['pfx_z']), 2) if pd.notna(row.get('pfx_z')) else None,
                        'release_extension': round(float(row['release_extension']), 1) if pd.notna(row.get('release_extension')) else None,
                        'effective_speed': round(float(row['effective_speed']), 1) if pd.notna(row.get('effective_speed')) else None
                    }
                    
                    # Get percentile analysis
                    percentile_analysis = self.percentile_analyzer.analyze_pitch_percentiles(pitch_data)
                    result['percentile_analysis'] = percentile_analysis
                    
                    # Add percentile highlights
                    if percentile_analysis.get('percentiles'):
                        highlights = []
                        elite_metrics = []
                        
                        for metric_name, data in percentile_analysis['percentiles'].items():
                            percentile = data['percentile']
                            description = self.percentile_analyzer.get_percentile_description(percentile)
                            
                            if percentile >= 95:
                                elite_metrics.append(f"Elite {metric_name}")
                                highlights.append(f"Elite {metric_name} ({percentile:.1f}th percentile)")
                            elif percentile >= 85:
                                highlights.append(f"Excellent {metric_name} ({percentile:.1f}th percentile)")
                            elif percentile >= 75:
                                highlights.append(f"Above Average {metric_name} ({percentile:.1f}th percentile)")
                            elif percentile <= 15:
                                highlights.append(f"Poor {metric_name} ({percentile:.1f}th percentile)")
                            elif percentile <= 25:
                                highlights.append(f"Below Average {metric_name} ({percentile:.1f}th percentile)")
                        
                        result['percentile_highlights'] = highlights
                        result['elite_metrics'] = elite_metrics
                        
                        # Add a summary of what made this pitch special
                        if elite_metrics:
                            result['what_made_it_special'] = f"This {result['pitch_name'].lower()} had {', '.join(elite_metrics).lower()}, making it exceptionally deceptive"
                        
                        # Add expert AI analysis with proper timeout handling
                        try:
                            expert_analysis = self._get_expert_analysis(row, result, percentile_analysis)
                            if expert_analysis:
                                result['expert_analysis'] = expert_analysis
                            else:
                                result['expert_analysis'] = None
                        except Exception as e:
                            logger.warning(f"Expert analysis failed: {e}")
                            result['expert_analysis'] = None
                        
                except Exception as e:
                    logger.warning(f"Error adding percentile analysis: {e}")
                    result['percentile_analysis'] = None
            results.append(result)
        
        return results
    
    def _get_expert_analysis(self, row, result, percentile_analysis):
        """
        Get expert AI analysis using OpenRouter Claude Sonnet
        """
        try:
            openrouter_api_key = os.environ.get('OPENROUTER_API_KEY')
            if not openrouter_api_key:
                logger.warning("No OpenRouter API key found")
                return None
            
            # Prepare pitch and swing data for AI analysis
            def safe_float(value, default=0):
                try:
                    return float(value) if value is not None else default
                except (ValueError, TypeError):
                    return default
            
            pitch_data = {
                'pitch_type': result.get('pitch_name', 'Unknown'),
                'velocity': safe_float(result.get('release_speed')),
                'spin_rate': safe_float(result.get('release_spin_rate')),
                'horizontal_break': safe_float(self._safe_get(row, 'pfx_x', 0)),
                'vertical_break': safe_float(self._safe_get(row, 'pfx_z', 0)),
                'plate_x': safe_float(result.get('plate_x')),
                'plate_z': safe_float(result.get('plate_z')),
                'sz_top': safe_float(result.get('sz_top'), 3.5),
                'sz_bot': safe_float(result.get('sz_bot'), 1.5),
                'bat_speed': safe_float(result.get('bat_speed')),
                'swing_tilt': safe_float(result.get('swing_path_tilt')),
                'intercept_y': safe_float(result.get('intercept_ball_minus_batter_pos_y_inches')),
                'sword_score': safe_float(result.get('sword_score'))
            }
            
            # Create analysis prompt
            prompt = f"""Role & Task:

You are a baseball analyst specialized in pitch quality and batter performance analysis. Your task is to quickly and clearly determine why a given swing-and-miss pitch resulted in a strikeout ("sword") based solely on provided raw Statcast data.

Data Provided (Statcast):
• Pitch Metrics:
  - Pitch type: {pitch_data['pitch_type']}
  - Pitch velocity: {pitch_data['velocity']} MPH
  - Spin rate: {pitch_data['spin_rate']} RPM
  - Vertical break: {pitch_data['vertical_break']:.2f} inches
  - Horizontal break: {pitch_data['horizontal_break']:.2f} inches
  - Plate X (horizontal location): {pitch_data['plate_x']:.2f} (negative = inside to RHH)
  - Plate Z (vertical location): {pitch_data['plate_z']:.2f} feet
  - Strike zone top: {pitch_data['sz_top']:.2f} ft
  - Strike zone bottom: {pitch_data['sz_bot']:.2f} ft

• Batter Swing Metrics:
  - Bat speed: {pitch_data['bat_speed']} MPH
  - Intercept Y (timing): {pitch_data['intercept_y']:.1f} inches behind ball
  - Swing path tilt: {pitch_data['swing_tilt']:.1f} degrees
  - Sword Score: {pitch_data['sword_score']}/100

Your Output (Concise, Sharp Analysis):

In one or two concise sentences, provide your expert assessment, clearly stating:
1. Pitch Quality: Is this pitch elite (top 20% in spin, velo, break, or location)? Average? Below average?
2. Batter Performance: Was the batter genuinely fooled by pitch movement, speed, location, or was the swing simply poorly timed or executed by the batter?
3. Sword Verdict: Clearly state if this strikeout was mostly due to exceptional pitch quality ("Pitcher's sword") or batter error ("Batter's fail").

Use engaging, viral-friendly language. Be sarcastic or witty if the situation clearly warrants it, but remain professional and baseball-smart.

Goal:
Your analysis should quickly inform baseball-savvy audiences why this swing-and-miss was a "sword" and if the batter or pitcher deserves the credit (or blame).
Your phrasing should be witty and concise enough to be instantly sharable and memorable on social media."""

            # Make API call to OpenRouter
            headers = {
                'Authorization': f'Bearer {openrouter_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'anthropic/claude-3.5-sonnet',
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': 200,
                'temperature': 0.7
            }
            
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    analysis = data['choices'][0]['message']['content'].strip()
                    logger.debug(f"Expert analysis generated: {analysis[:100]}...")
                    return analysis
                else:
                    logger.warning("No analysis returned from OpenRouter")
                    return None
            else:
                logger.warning(f"OpenRouter API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.warning(f"Error generating expert analysis: {e}")
            return None
    
    def _get_mp4_download_url(self, play_id, max_retries=3):
        """
        Extract the direct MP4 download URL from a Baseball Savant sporty-videos page
        
        Args:
            play_id (str): The UUID playId for the pitch
            max_retries (int): Number of retry attempts
            
        Returns:
            str: Direct MP4 URL if found, None otherwise
        """
        attempt = 0
        while attempt < max_retries:
            try:
                from bs4 import BeautifulSoup
                
                page_url = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}"
                logger.debug(f"Extracting MP4 from: {page_url} (attempt {attempt + 1})")
                
                response = requests.get(page_url, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                video_container = soup.find('div', class_='video-box')
                
                if video_container:
                    video_tag = video_container.find('video')
                    if video_tag:
                        source_tag = video_tag.find('source', {'type': 'video/mp4'})
                        if source_tag and source_tag.get('src'):
                            mp4_url = source_tag.get('src')
                            logger.debug(f"Found MP4 URL for playId {play_id}: {mp4_url}")
                            return mp4_url
                
                logger.debug(f"No video URL found for playId {play_id} on attempt {attempt + 1}")
                attempt += 1
                if attempt < max_retries:
                    import time
                    time.sleep(1)  # Brief wait before retry
                    
            except Exception as e:
                logger.debug(f"Error extracting MP4 for playId {play_id} on attempt {attempt + 1}: {str(e)}")
                attempt += 1
                if attempt < max_retries:
                    import time
                    time.sleep(1)
        
        return None
    
    def _get_pitch_name(self, pitch_type):
        """
        Convert pitch type abbreviation to full pitch name
        """
        pitch_names = {
            'FF': 'Four-Seam Fastball',
            'SI': 'Sinker',
            'FC': 'Cutter',
            'SL': 'Slider',
            'CU': 'Curveball',
            'KC': 'Knuckle Curve',
            'CH': 'Changeup',
            'FS': 'Splitter',
            'KN': 'Knuckleball',
            'EP': 'Eephus',
            'SC': 'Screwball',
            'FO': 'Forkball'
        }
        return pitch_names.get(pitch_type, pitch_type)
    
    def _safe_get(self, row, column, default):
        """
        Safely get a value from a pandas row with a default fallback
        """
        try:
            value = row.get(column, default)
            if pd.isna(value) or value == '':
                return default
            return str(value)
        except:
            return default
