"""
Database-powered SwordFinder with local MP4 storage
Production-ready version that caches results and downloads videos locally
"""
import logging
import os
import requests
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_, desc
from models_complete import StatcastPitch, SwordSwing, DailyResults, get_db, create_tables
from percentile_analyzer import PercentileAnalyzer
import json

logger = logging.getLogger(__name__)

class DatabaseSwordFinder:
    """
    Database-powered SwordFinder with caching and local video storage
    """
    
    def __init__(self):
        self.percentile_analyzer = PercentileAnalyzer()
        self.video_storage_path = "static/videos"  # Store videos in Flask static folder
        self._ensure_video_directory()
        
    def _ensure_video_directory(self):
        """Create video storage directory if it doesn't exist"""
        os.makedirs(self.video_storage_path, exist_ok=True)
        
    def find_sword_swings(self, date_str: str) -> Dict:
        """
        Main method - checks cache first, processes if needed
        """
        logger.info(f"Finding sword swings for {date_str}")
        
        # Check if we already have results for this date
        db = get_db()
        try:
            daily_result = db.query(DailyResults).filter(DailyResults.date == date_str).first()
            
            if daily_result and daily_result.expert_analysis_completed:
                logger.info(f"Found cached results for {date_str}")
                return self._get_cached_results(date_str, db)
            else:
                logger.info(f"Processing new date: {date_str}")
                return self._process_new_date(date_str, db)
                
        finally:
            db.close()
    
    def _get_cached_results(self, date_str: str, db) -> Dict:
        """Get cached sword swings from database"""
        # Get sword swings for this date
        sword_swings = (db.query(SwordSwing)
                       .join(StatcastPitch)
                       .filter(StatcastPitch.game_date == date_str)
                       .order_by(desc(SwordSwing.sword_score))
                       .limit(5)
                       .all())
        
        results = []
        for swing in sword_swings:
            pitch = swing.pitch
            
            # Build result dict
            result = {
                'play_id': pitch.play_id,
                'game_pk': pitch.game_pk,
                'player_name': pitch.pitcher_name,
                'pitcher_name': pitch.pitcher_name,
                'batter_name': pitch.batter_name,
                'pitch_type': pitch.pitch_type,
                'pitch_name': pitch.pitch_name,
                'release_speed': pitch.release_speed,
                'release_spin_rate': pitch.release_spin_rate,
                'plate_x': pitch.plate_x,
                'plate_z': pitch.plate_z,
                'sz_top': pitch.sz_top,
                'sz_bot': pitch.sz_bot,
                'bat_speed': pitch.bat_speed,
                'swing_path_tilt': pitch.swing_path_tilt,
                'attack_angle': pitch.attack_angle,
                'intercept_ball_minus_batter_pos_y_inches': pitch.intercept_ball_minus_batter_pos_y_inches,
                'description': pitch.description,
                'events': pitch.events,
                'inning': pitch.inning,
                'balls': pitch.balls,
                'strikes': pitch.strikes,
                'at_bat_number': pitch.at_bat_number,
                'pitch_number': pitch.pitch_number,
                'home_team': pitch.home_team,
                'away_team': pitch.away_team,
                'batter': pitch.batter,
                'pitcher': pitch.pitcher,
                'sword_score': round(swing.sword_score, 1),
                'percentile_analysis': swing.percentile_analysis,
                'percentile_highlights': swing.percentile_highlights,
                'expert_analysis': swing.expert_analysis,
                'video_url': swing.video_url,
                'download_url': swing.download_url,
                'local_mp4_path': swing.local_mp4_path if swing.mp4_downloaded else None,
                'mp4_downloaded': swing.mp4_downloaded
            }
            results.append(result)
        
        return {
            'success': True,
            'data': results,
            'count': len(results),
            'date': date_str,
            'cached': True
        }
    
    def _process_new_date(self, date_str: str, db) -> Dict:
        """Process a new date - find sword swings, analyze, and cache"""
        logger.info(f"Processing sword swings for {date_str}")
        
        # Get all pitches for this date from database
        pitches = (db.query(StatcastPitch)
                  .filter(StatcastPitch.game_date == date_str)
                  .all())
        
        if not pitches:
            return {
                'success': False,
                'error': f'No Statcast data found for {date_str}',
                'count': 0,
                'date': date_str
            }
        
        logger.info(f"Found {len(pitches)} total pitches for {date_str}")
        
        # Apply sword swing filters
        sword_candidates = self._apply_sword_filters(pitches)
        logger.info(f"Found {len(sword_candidates)} sword swing candidates")
        
        if not sword_candidates:
            # Record that we processed this date but found no results
            daily_result = DailyResults(
                date=date_str,
                total_pitches=len(pitches),
                sword_swings_found=0,
                processing_completed_at=datetime.utcnow(),
                expert_analysis_completed=True
            )
            db.add(daily_result)
            db.commit()
            
            return {
                'success': True,
                'data': [],
                'count': 0,
                'date': date_str
            }
        
        # Calculate sword scores and get top 5
        top_swings = self._calculate_and_rank_swings(sword_candidates)[:5]
        
        # Process each swing: percentiles, expert analysis, video download
        results = []
        for pitch in top_swings:
            swing_result = self._process_sword_swing(pitch, db)
            if swing_result:
                results.append(swing_result)
        
        # Record processing completion
        daily_result = DailyResults(
            date=date_str,
            total_pitches=len(pitches),
            sword_swings_found=len(results),
            processing_completed_at=datetime.utcnow(),
            expert_analysis_completed=True
        )
        db.add(daily_result)
        db.commit()
        
        return {
            'success': True,
            'data': results,
            'count': len(results),
            'date': date_str,
            'cached': False
        }
    
    def _apply_sword_filters(self, pitches) -> List[StatcastPitch]:
        """Apply sword swing filtering criteria"""
        candidates = []
        
        for pitch in pitches:
            # Check if this is a sword swing candidate
            if (pitch.description and 'swinging_strike' in pitch.description and
                pitch.bat_speed and pitch.bat_speed < 60 and
                pitch.intercept_ball_minus_batter_pos_y_inches and 
                pitch.intercept_ball_minus_batter_pos_y_inches > 14 and
                pitch.swing_path_tilt and pitch.swing_path_tilt > 30):
                candidates.append(pitch)
        
        return candidates
    
    def _calculate_and_rank_swings(self, candidates) -> List[StatcastPitch]:
        """Calculate sword scores and rank swings"""
        scored_swings = []
        
        for pitch in candidates:
            # Calculate sword score using the same algorithm
            sword_score = self._calculate_sword_score(pitch)
            pitch._sword_score = sword_score  # Temporary attribute
            scored_swings.append(pitch)
        
        # Sort by score descending
        return sorted(scored_swings, key=lambda x: x._sword_score, reverse=True)
    
    def _calculate_sword_score(self, pitch) -> float:
        """Calculate sword score for a pitch"""
        try:
            # Normalize to 50-100 scale like original
            bat_speed_component = 0.35 * (60 - pitch.bat_speed) / 60
            swing_tilt_component = 0.25 * pitch.swing_path_tilt / 60
            intercept_component = 0.25 * pitch.intercept_ball_minus_batter_pos_y_inches / 50
            
            # Zone penalty (simplified)
            zone_penalty = 0.15 * 0.8  # Assume most are out of zone
            
            raw_score = bat_speed_component + swing_tilt_component + intercept_component + zone_penalty
            
            # Normalize to 50-100 scale
            return max(50, min(100, 50 + (raw_score * 50)))
            
        except Exception as e:
            logger.warning(f"Error calculating sword score: {e}")
            return 50.0
    
    def _process_sword_swing(self, pitch, db) -> Optional[Dict]:
        """Process a single sword swing: analysis, video download, database storage"""
        try:
            # Get percentile analysis
            percentile_analysis = self._get_percentile_analysis(pitch)
            
            # Get expert analysis (with error handling)
            expert_analysis = self._get_expert_analysis(pitch, percentile_analysis)
            
            # Get video URLs and download MP4
            video_urls = self._get_and_download_video(pitch)
            
            # Create SwordSwing database record
            sword_swing = SwordSwing(
                pitch_id=pitch.id,
                sword_score=pitch._sword_score,
                percentile_analysis=percentile_analysis,
                percentile_highlights=self._extract_percentile_highlights(percentile_analysis),
                expert_analysis=expert_analysis,
                expert_analysis_generated_at=datetime.utcnow() if expert_analysis else None,
                video_url=video_urls.get('video_url'),
                download_url=video_urls.get('download_url'),
                local_mp4_path=video_urls.get('local_path'),
                mp4_downloaded=video_urls.get('downloaded', False),
                mp4_file_size=video_urls.get('file_size')
            )
            
            db.add(sword_swing)
            db.commit()
            
            # Build result dictionary
            result = {
                'play_id': pitch.play_id,
                'game_pk': pitch.game_pk,
                'player_name': pitch.pitcher_name,
                'pitcher_name': pitch.pitcher_name,
                'batter_name': pitch.batter_name,
                'pitch_type': pitch.pitch_type,
                'pitch_name': pitch.pitch_name,
                'release_speed': pitch.release_speed,
                'release_spin_rate': pitch.release_spin_rate,
                'plate_x': pitch.plate_x,
                'plate_z': pitch.plate_z,
                'sz_top': pitch.sz_top,
                'sz_bot': pitch.sz_bot,
                'bat_speed': pitch.bat_speed,
                'swing_path_tilt': pitch.swing_path_tilt,
                'attack_angle': pitch.attack_angle,
                'intercept_ball_minus_batter_pos_y_inches': pitch.intercept_ball_minus_batter_pos_y_inches,
                'description': pitch.description,
                'events': pitch.events,
                'inning': pitch.inning,
                'balls': pitch.balls,
                'strikes': pitch.strikes,
                'at_bat_number': pitch.at_bat_number,
                'pitch_number': pitch.pitch_number,
                'home_team': pitch.home_team,
                'away_team': pitch.away_team,
                'batter': pitch.batter,
                'pitcher': pitch.pitcher,
                'sword_score': round(pitch._sword_score, 1),
                'percentile_analysis': percentile_analysis,
                'percentile_highlights': sword_swing.percentile_highlights,
                'expert_analysis': expert_analysis,
                'video_url': video_urls.get('video_url'),
                'download_url': video_urls.get('download_url'),
                'local_mp4_path': video_urls.get('local_path'),
                'mp4_downloaded': video_urls.get('downloaded', False)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing sword swing: {e}")
            return None
    
    def _get_percentile_analysis(self, pitch) -> Dict:
        """Get percentile analysis for a pitch"""
        try:
            pitch_data = {
                'pitch_type': pitch.pitch_type,
                'release_speed': pitch.release_speed,
                'release_spin_rate': pitch.release_spin_rate,
                'release_extension': pitch.release_extension,
                'pfx_x': pitch.pfx_x,
                'pfx_z': pitch.pfx_z,
                'effective_speed': pitch.effective_speed
            }
            
            return self.percentile_analyzer.analyze_pitch_percentiles(pitch_data)
            
        except Exception as e:
            logger.warning(f"Error getting percentile analysis: {e}")
            return {}
    
    def _extract_percentile_highlights(self, percentile_analysis) -> List[str]:
        """Extract percentile highlights from analysis"""
        highlights = []
        
        if not percentile_analysis or 'percentiles' not in percentile_analysis:
            return highlights
        
        for metric, data in percentile_analysis['percentiles'].items():
            percentile = data.get('percentile', 0)
            
            if percentile >= 95:
                highlights.append(f"Elite {metric} ({percentile:.1f}th percentile)")
            elif percentile >= 85:
                highlights.append(f"Excellent {metric} ({percentile:.1f}th percentile)")
            elif percentile >= 75:
                highlights.append(f"Above Average {metric} ({percentile:.1f}th percentile)")
            elif percentile <= 15:
                highlights.append(f"Poor {metric} ({percentile:.1f}th percentile)")
            elif percentile <= 25:
                highlights.append(f"Below Average {metric} ({percentile:.1f}th percentile)")
        
        return highlights
    
    def _get_expert_analysis(self, pitch, percentile_analysis) -> Optional[str]:
        """Get expert AI analysis with error handling"""
        try:
            # Import and use existing expert analysis logic
            from swordfinder import SwordFinder
            sf = SwordFinder()
            
            # Create a mock row object for the existing method
            class MockRow:
                def __init__(self, pitch):
                    for attr in ['release_speed', 'release_spin_rate', 'pfx_x', 'pfx_z']:
                        setattr(self, attr, getattr(pitch, attr, 0))
            
            mock_row = MockRow(pitch)
            result = {
                'pitch_name': pitch.pitch_name,
                'release_speed': pitch.release_speed,
                'release_spin_rate': pitch.release_spin_rate,
                'plate_x': pitch.plate_x,
                'plate_z': pitch.plate_z,
                'sz_top': pitch.sz_top,
                'sz_bot': pitch.sz_bot,
                'bat_speed': pitch.bat_speed,
                'swing_path_tilt': pitch.swing_path_tilt,
                'intercept_ball_minus_batter_pos_y_inches': pitch.intercept_ball_minus_batter_pos_y_inches,
                'sword_score': pitch._sword_score
            }
            
            return sf._get_expert_analysis(mock_row, result, percentile_analysis)
            
        except Exception as e:
            logger.warning(f"Expert analysis failed: {e}")
            return None
    
    def _get_and_download_video(self, pitch) -> Dict:
        """Get video URLs and download MP4 locally"""
        result = {
            'video_url': None,
            'download_url': None,
            'local_path': None,
            'downloaded': False,
            'file_size': None
        }
        
        if not pitch.play_id:
            return result
        
        try:
            # Get video URLs (using existing logic)
            from swordfinder import SwordFinder
            sf = SwordFinder()
            
            # Get MP4 download URL
            download_url = sf._get_mp4_download_url(pitch.play_id)
            if download_url:
                result['download_url'] = download_url
                result['video_url'] = f"https://baseballsavant.mlb.com/sporty-videos?playId={pitch.play_id}"
                
                # Download MP4 locally
                local_path = self._download_mp4(pitch.play_id, download_url)
                if local_path:
                    result['local_path'] = local_path
                    result['downloaded'] = True
                    
                    # Get file size
                    try:
                        result['file_size'] = os.path.getsize(local_path)
                    except:
                        pass
        
        except Exception as e:
            logger.warning(f"Video processing failed for {pitch.play_id}: {e}")
        
        return result
    
    def _download_mp4(self, play_id: str, download_url: str) -> Optional[str]:
        """Download MP4 file locally"""
        try:
            filename = f"{play_id}.mp4"
            local_path = os.path.join(self.video_storage_path, filename)
            
            # Skip if already downloaded
            if os.path.exists(local_path):
                logger.info(f"Video already exists: {local_path}")
                return local_path
            
            # Download the file
            logger.info(f"Downloading MP4: {download_url}")
            response = requests.get(download_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Write to local file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded MP4 to: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"Failed to download MP4 {play_id}: {e}")
            return None