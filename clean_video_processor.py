#!/usr/bin/env python3
"""
Enhanced Video Processor for SwordFinder
Based on proven Beautiful Soup techniques from:
- dylandru/BSav_Scraper_Vid (Baseball Savant scraping)
- coperyan/mlb-videos (MLB API approaches)
"""

import requests
import time
import logging
import os
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlencode

# Optional Azure import
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedSwordVideoProcessor:
    """
    Enhanced video processor using proven Beautiful Soup techniques:
    - Baseball Savant static scraping (BSav_Scraper_Vid approach)
    - MLB Film Room API (mlb-videos approach)
    - Multiple URL formats and parsing methods
    """
    
    def __init__(self, azure_connection_string: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Azure setup (optional) - try from env if not provided
        self.azure_client = None
        if AZURE_AVAILABLE:
            if not azure_connection_string:
                # Try to get from environment
                import os
                from dotenv import load_dotenv
                load_dotenv()
                azure_connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
            
            if azure_connection_string:
                self.azure_client = BlobServiceClient.from_connection_string(azure_connection_string)
                logger.info("✅ Azure Blob Storage client initialized")
        
        # MLB API endpoints
        self.mlb_api_base = "https://statsapi.mlb.com/api/v1"
        self.film_room_base = "https://www.mlb.com/video/search"
        self.baseball_savant_base = "https://baseballsavant.mlb.com"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests
    
    def _rate_limit(self):
        """Respect rate limits to avoid getting blocked"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def get_play_video_via_baseball_savant(self, play_id: str) -> Optional[str]:
        """
        Method 1: Baseball Savant scraping (BSav_Scraper_Vid approach)
        Uses Beautiful Soup to parse static HTML and find video URLs
        """
        self._rate_limit()
        
        try:
            # Try multiple URL formats (from BSav_Scraper_Vid research)
            url_formats = [
                f"{self.baseball_savant_base}/sporty-videos?playId={play_id}",
                f"{self.baseball_savant_base}/sporty-videos?playId={play_id}&videoType=AWAY",
                f"{self.baseball_savant_base}/sporty-videos?playId={play_id}&videoType=HOME",
                f"{self.baseball_savant_base}/sporty-videos?playId={play_id}&videoType=NETWORK",
            ]
            
            for video_page_url in url_formats:
                logger.debug(f"Trying Baseball Savant: {video_page_url}")
                
                response = self.session.get(video_page_url, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Method A: Direct video tag (from BSav_Scraper_Vid)
                video_container = soup.find('div', class_='video-box')
                if video_container:
                    video_tag = video_container.find('video')
                    if video_tag:
                        source_tag = video_tag.find('source', {'type': 'video/mp4'})
                        if source_tag:
                            video_url = source_tag.get('src')
                            if video_url and not video_url.startswith('data:'):
                                logger.info(f"✅ Baseball Savant (direct) found video: {video_url}")
                                return video_url
                
                # Method B: JavaScript parsing (enhanced patterns)
                scripts = soup.find_all('script')
                for script in scripts:
                    script_content = script.get_text() if script else ""
                    if script_content:
                        # Multiple regex patterns for video URLs (from research)
                        patterns = [
                            r'"videoUrl":\s*"([^"]+)"',
                            r'"playbacks":\s*\[{"url":\s*"([^"]+)"',
                            r'"mp4Avc".*?"url":\s*"([^"]+)"',
                            r'(https://[^"\s]*\.mp4[^"\s]*)',
                            r'"(https://.*?mlb.*?\.mp4.*?)"',
                            r'"src":\s*"(https://[^"]*\.mp4[^"]*)"',
                            r'video_url["\s]*:["\s]*"([^"]*)"',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, script_content)
                            for match in matches:
                                if 'mp4' in match and 'http' in match:
                                    # Clean up URL (remove escape chars)
                                    clean_url = match.replace('\\', '').strip()
                                    if len(clean_url) > 20:  # Basic validation
                                        logger.info(f"✅ Baseball Savant (script) found video: {clean_url}")
                                        return clean_url
                
                # Method C: Look for any video URLs in the page source
                page_text = soup.get_text()
                video_url_pattern = r'(https://[^\s"\']*\.mp4[^\s"\']*)'
                matches = re.findall(video_url_pattern, page_text)
                for match in matches:
                    if 'mlb' in match.lower() and len(match) > 30:
                        clean_url = match.strip()
                        logger.info(f"✅ Baseball Savant (text) found video: {clean_url}")
                        return clean_url
            
            logger.debug(f"No video found via Baseball Savant for play_id {play_id}")
            return None
            
        except Exception as e:
            logger.debug(f"Baseball Savant scraping failed for play_id {play_id}: {e}")
            return None
    
    def get_play_video_via_mlb_film_room(self, game_pk: str, play_id: str) -> Optional[str]:
        """
        Method 2: MLB Film Room API (mlb-videos approach)
        Uses MLB's video search API
        """
        self._rate_limit()
        
        try:
            # Film Room search parameters (from mlb-videos research)
            search_params = {
                'game_pk': game_pk,
                'play_id': play_id,
                'feed': 'Best',
                'format': 'json'
            }
            
            film_room_url = f"{self.film_room_base}?{urlencode(search_params)}"
            logger.debug(f"Trying MLB Film Room API: {film_room_url}")
            
            response = self.session.get(film_room_url, timeout=15)
            response.raise_for_status()
            
            # Try to parse as JSON first
            try:
                data = response.json()
                if 'videos' in data and data['videos']:
                    video_data = data['videos'][0]  # Get first/best video
                    if 'playbacks' in video_data:
                        # Find highest quality playback
                        playbacks = video_data['playbacks']
                        for playback in playbacks:
                            if playback.get('name') == 'mp4Avc':
                                video_url = playback.get('url')
                                if video_url:
                                    logger.info(f"✅ MLB Film Room found video: {video_url}")
                                    return video_url
            except json.JSONDecodeError:
                # Response might be HTML, try parsing it
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for video JSON data in script tags
                scripts = soup.find_all('script')
                for script in scripts:
                    script_content = script.get_text() if script else ""
                    if script_content and 'video' in script_content.lower():
                        # Try to extract video URL from embedded JSON
                        try:
                            json_match = re.search(r'({.*"playbacks".*})', script_content)
                            if json_match:
                                video_data = json.loads(json_match.group(1))
                                if 'playbacks' in video_data:
                                    for playback in video_data['playbacks']:
                                        if playback.get('name') == 'mp4Avc':
                                            video_url = playback.get('url')
                                            if video_url:
                                                logger.info(f"✅ MLB Film Room (parsed) found video: {video_url}")
                                                return video_url
                        except (json.JSONDecodeError, KeyError):
                            continue
            
            logger.debug(f"No video found via MLB Film Room for game_pk={game_pk}, play_id={play_id}")
            return None
            
        except Exception as e:
            logger.debug(f"MLB Film Room API failed for game_pk={game_pk}, play_id={play_id}: {e}")
            return None
    
    def get_play_video_via_mlb_stats_api(self, game_pk: str, play_id: str) -> Optional[str]:
        """
        Method 3: MLB Stats API direct approach
        Sometimes provides direct video links in game content
        """
        self._rate_limit()
        
        try:
            # MLB Stats API endpoint for game highlights
            api_url = f"{self.mlb_api_base}/game/{game_pk}/content"
            logger.debug(f"Trying MLB Stats API: {api_url}")
            
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Look for highlights that match our play_id
            if 'highlights' in data and 'highlights' in data['highlights']:
                highlights = data['highlights']['highlights']['items']
                
                for highlight in highlights:
                    # Check if this highlight matches our play
                    if 'playId' in highlight and highlight['playId'] == play_id:
                        if 'playbacks' in highlight:
                            # Find best quality playback
                            for playback in highlight['playbacks']:
                                if playback.get('name') == 'mp4Avc':
                                    video_url = playback.get('url')
                                    if video_url:
                                        logger.info(f"✅ MLB Stats API found video: {video_url}")
                                        return video_url
            
            logger.debug(f"No video found via MLB Stats API for game_pk={game_pk}, play_id={play_id}")
            return None
            
        except Exception as e:
            logger.debug(f"MLB Stats API failed for game_pk={game_pk}, play_id={play_id}: {e}")
            return None
    
    def get_video_url_for_play(self, game_pk: str, play_id: str) -> Optional[str]:
        """
        Get video URL using multi-source strategy:
        1. Baseball Savant scraping (most reliable for individual pitches)
        2. MLB Film Room API (good for highlights)
        3. MLB Stats API (backup)
        """
        logger.info(f"🎥 Getting video for game_pk={game_pk}, play_id={play_id}")
        
        # Method 1: Baseball Savant scraping (primary for pitch-level videos)
        logger.debug("Trying Method 1: Baseball Savant scraping")
        video_url = self.get_play_video_via_baseball_savant(play_id)
        if video_url:
            return video_url
        
        # Method 2: MLB Film Room API
        logger.debug("Trying Method 2: MLB Film Room API")
        video_url = self.get_play_video_via_mlb_film_room(game_pk, play_id)
        if video_url:
            return video_url
        
        # Method 3: MLB Stats API
        logger.debug("Trying Method 3: MLB Stats API")
        video_url = self.get_play_video_via_mlb_stats_api(game_pk, play_id)
        if video_url:
            return video_url
        
        logger.error(f"❌ No video found for play_id {play_id} using any method")
        return None
    
    def download_video_locally(self, video_url: str, local_path: str) -> bool:
        """Download video to local file system"""
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            logger.info(f"📥 Downloading video to {local_path}")
            
            with self.session.get(video_url, stream=True, timeout=30) as response:
                response.raise_for_status()
                
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            logger.info(f"✅ Video downloaded successfully to {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Video download failed: {e}")
            return False
    
    def upload_video_to_azure(self, video_url: str, blob_name: str) -> Optional[str]:
        """Upload video directly to Azure Blob Storage"""
        if not self.azure_client:
            logger.warning("Azure client not initialized")
            return None
        
        try:
            logger.info(f"☁️ Uploading video to Azure: {blob_name}")
            
            # Stream download directly to Azure
            with self.session.get(video_url, stream=True, timeout=30) as response:
                response.raise_for_status()
                
                blob_client = self.azure_client.get_blob_client(
                    container="swordfinder-videos", 
                    blob=blob_name
                )
                
                blob_client.upload_blob(
                    response.iter_content(chunk_size=8192),
                    blob_type="BlockBlob",
                    overwrite=True,
                    content_settings=ContentSettings(content_type='video/mp4') if AZURE_AVAILABLE else None
                )
                
                azure_url = blob_client.url
                logger.info(f"✅ Video uploaded to Azure: {azure_url}")
                return azure_url
                
        except Exception as e:
            logger.error(f"❌ Azure upload failed: {e}")
            return None
    
    def process_sword_video(self, game_pk: str, play_id: str, 
                          local_download: bool = True, 
                          azure_upload: bool = True) -> Dict[str, Any]:
        """
        Process a single sword swing video with comprehensive fallback strategy
        """
        result = {
            'success': False,
            'video_url': None,
            'local_path': None,
            'azure_url': None,
            'method_used': None,
            'error': None
        }
        
        try:
            # Get video URL using multi-source strategy
            video_url = self.get_video_url_for_play(game_pk, play_id)
            
            if not video_url:
                result['error'] = 'No video URL found using any method'
                return result
            
            result['video_url'] = video_url
            result['success'] = True
            
            # Determine which method was used (for logging/analytics)
            if 'mlb.com' in video_url:
                result['method_used'] = 'MLB Film Room API'
            elif 'baseballsavant' in video_url or 'mlb' in video_url:
                result['method_used'] = 'Baseball Savant Scraping'
            elif 'statsapi' in video_url:
                result['method_used'] = 'MLB Stats API'
            else:
                result['method_used'] = 'Unknown'
            
            # Local download
            if local_download:
                local_path = f"test_videos/{play_id}.mp4"
                if self.download_video_locally(video_url, local_path):
                    result['local_path'] = local_path
            
            # Azure upload
            if azure_upload and self.azure_client:
                blob_name = f"sword_swings/{play_id}.mp4"
                azure_url = self.upload_video_to_azure(video_url, blob_name)
                if azure_url:
                    result['azure_url'] = azure_url
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Video processing failed for {play_id}: {e}")
            return result

def main():
    """Test the video processor with sample data"""
    processor = EnhancedSwordVideoProcessor()
    
    # Test with sample sword swing data
    test_data = [
        {
            'game_pk': '777785',
            'sv_id': '599c588e-d41d-3ae6-ad6a-c20a2024f3a9',
            'description': 'Test pitch video download'
        }
    ]
    
    print("🧪 Testing Enhanced Video Processor")
    print("=" * 50)
    
    results = processor.process_sword_video(test_data[0]['game_pk'], test_data[0]['sv_id'])
    
    print("\n📊 Results:")
    print(f"Success: {results['success']}")
    print(f"Video URL: {results['video_url']}")
    print(f"Local Path: {results['local_path']}")
    print(f"Azure URL: {results['azure_url']}")
    print(f"Method Used: {results['method_used']}")
    if results['error']:
        print(f"Error: {results['error']}")

if __name__ == "__main__":
    main() 