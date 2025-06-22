#!/usr/bin/env python3
"""
SWORDFINDER v2 - PHASE 2: TOP SWORD VIDEO PROCESSING
====================================================

Processes videos for the top 5 sword swings per day from our complete dataset.
- Queries database for ~125 top sword candidates  
- Downloads videos from Baseball Savant/MLB Film Room
- Uploads to Azure Blob Storage with CDN URLs
- Updates database with video metadata

Strategy: Quality over quantity - focus on the most impressive sword swings
Cost: <$0.05/month for ~650MB of premium video content
"""

import pandas as pd
import time
from datetime import datetime, timedelta
from supabase import create_client, Client
from clean_video_processor import SwordVideoProcessor
import os
from dotenv import load_dotenv
import argparse

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

class TopSwordVideoProcessor:
    """
    Processes videos for top sword swings per day with Azure integration
    """
    
    def __init__(self):
        # Initialize Supabase client
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Missing Supabase credentials in environment variables")
        
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase client created")
        
        # Initialize video processor
        if not AZURE_CONNECTION_STRING:
            raise ValueError("Missing Azure connection string in environment variables")
            
        self.video_processor = SwordVideoProcessor(
            azure_connection_string=AZURE_CONNECTION_STRING
        )
        print("✅ Video processor initialized")
    
    def get_top_swords_for_processing(self, limit_days=None):
        """
        Get top 5 sword swings per day that need video processing
        
        Args:
            limit_days: If specified, only process this many days (for testing)
        """
        print("🔍 Querying top sword swings per day...")
        
        try:
            # Get sword candidates that need video processing
            query = (
                self.supabase.table("statcast_pitches")
                .select("id, game_date, game_pk, play_id, pitcher_name, batter_name, sword_score, raw_sword_metric, video_downloaded, azure_blob_url")
                .eq("is_sword_candidate", True)
                .eq("video_downloaded", False)
                .not_.is_("play_id", "null")
                .order("game_date")
                .order("sword_score", desc=True)
            )
            
            if limit_days:
                query = query.limit(limit_days * 5)
            
            result = query.execute()
            
            # Handle the response safely
            candidates = getattr(result, 'data', []) or []
            
            if candidates:
                print(f"📊 Found {len(candidates)} sword swing candidates needing video processing")
                
                # Group by date and take top 5 per day
                daily_groups = {}
                for record in candidates:
                    date = record['game_date']
                    if date not in daily_groups:
                        daily_groups[date] = []
                    daily_groups[date].append(record)
                
                # Get top 5 per day
                top_per_day = []
                for date, records in daily_groups.items():
                    # Sort by sword_score descending and take top 5
                    sorted_records = sorted(records, key=lambda x: x.get('sword_score', 0) or 0, reverse=True)
                    top_per_day.extend(sorted_records[:5])
                
                print(f"📅 Spanning {len(daily_groups)} dates")
                print(f"📈 Top 5 per day: {len(top_per_day)} total candidates")
                
                return top_per_day
            else:
                print("ℹ️  No sword swings found needing video processing")
                return []
                
        except Exception as e:
            print(f"❌ Error querying top swords: {e}")
            return []
    
    def process_video_batch(self, sword_records, batch_size=5):
        """
        Process a batch of sword swings for video download/upload
        
        Args:
            sword_records: List of sword swing records from database
            batch_size: Number of videos to process at once
        """
        print(f"🎥 Processing videos for {len(sword_records)} sword swings...")
        
        processed_count = 0
        failed_count = 0
        
        for i in range(0, len(sword_records), batch_size):
            batch = sword_records[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(sword_records) + batch_size - 1) // batch_size
            
            print(f"\n📦 Batch {batch_num}/{total_batches}: Processing {len(batch)} videos...")
            
            for record in batch:
                success = self._process_single_video(record)
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
                
                # Brief pause between videos to be respectful
                time.sleep(2)
        
        print(f"\n🎉 Video processing complete!")
        print(f"✅ Successfully processed: {processed_count}")
        print(f"❌ Failed: {failed_count}")
        if processed_count + failed_count > 0:
            print(f"📈 Success rate: {(processed_count/(processed_count+failed_count)*100):.1f}%")
        
        return processed_count, failed_count
    
    def _process_single_video(self, record):
        """
        Process a single sword swing video
        
        Args:
            record: Database record with sword swing data
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            record_id = record['id']
            game_pk = str(record['game_pk'])
            play_id = record['play_id']
            pitcher_name = record.get('pitcher_name', 'Unknown')
            batter_name = record.get('batter_name', 'Unknown')
            sword_score = record.get('sword_score', 0)
            game_date = record['game_date']
            
            print(f"⚔️  Processing: {pitcher_name} vs {batter_name} (Score: {sword_score}) - {game_date}")
            
            # Prepare sword swing data for video processor
            sword_swing_data = {
                'game_pk': game_pk,
                'play_id': play_id,
                'sv_id': play_id,  # Use play_id as sv_id
                'pitcher_name': pitcher_name,
                'batter_name': batter_name
            }
            
            # Process video using the sword video processor
            result = self.video_processor.process_sword_swing_video(sword_swing_data)
            
            if result.get('success') and result.get('blob_url'):
                # Update database with video metadata
                self._update_video_metadata(record_id, result)
                blob_url = result['blob_url']
                print(f"   ✅ Video uploaded: {blob_url[:60]}...")
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"   ❌ Video processing failed: {error_msg}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error processing video: {e}")
            return False
    
    def _update_video_metadata(self, record_id, video_result):
        """
        Update database with video URLs and metadata
        
        Args:
            record_id: Database record ID
            video_result: Result from video processor
        """
        try:
            update_data = {
                'video_url': video_result.get('video_url'),
                'azure_blob_url': video_result.get('blob_url'),
                'video_downloaded': True,
                'video_processed_at': datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("statcast_pitches").update(update_data).eq('id', record_id).execute()
            
            # Check if update was successful
            update_successful = getattr(result, 'data', []) or []
            if not update_successful:
                print(f"   ⚠️  Database update may have failed for record {record_id}")
                
        except Exception as e:
            print(f"   ❌ Error updating database: {e}")
    
    def verify_results(self):
        """
        Verify that videos were processed correctly
        """
        print("🔍 VERIFYING VIDEO PROCESSING RESULTS")
        print("=" * 50)
        
        try:
            # Query processed videos
            result = self.supabase.table("statcast_pitches").select(
                "id, game_date, pitcher_name, batter_name, sword_score, azure_blob_url, video_downloaded"
            ).eq("is_sword_candidate", True).eq("video_downloaded", True).not_.is_("play_id", "null").execute()
            
            processed_videos = getattr(result, 'data', []) or []
            
            if processed_videos:
                print(f"📊 Total videos processed: {len(processed_videos)}")
                print(f"🔗 Azure URLs available: {len([v for v in processed_videos if v.get('azure_blob_url')])}")
                
                # Show top processed videos
                sorted_videos = sorted(processed_videos, key=lambda x: x.get('sword_score', 0) or 0, reverse=True)
                
                print(f"\n🏆 TOP PROCESSED SWORD VIDEOS:")
                for i, video in enumerate(sorted_videos[:10], 1):
                    print(f"  #{i}: {video.get('pitcher_name', 'Unknown')} vs {video.get('batter_name', 'Unknown')} "
                          f"(Score: {video.get('sword_score', 0)}) - {video.get('game_date', 'Unknown')}")
                    if video.get('azure_blob_url'):
                        print(f"      CDN: {video['azure_blob_url'][:80]}...")
            else:
                print("ℹ️  No processed videos found")
            
            print("\n✅ Verification complete!")
            
        except Exception as e:
            print(f"❌ Error during verification: {e}")

def main():
    """
    Main function with command line options
    """
    parser = argparse.ArgumentParser(description='Process top sword swing videos')
    parser.add_argument('--query-only', action='store_true', 
                       help='Only query and show candidates, do not process videos')
    parser.add_argument('--verify', action='store_true',
                       help='Only verify existing results')
    parser.add_argument('--limit-days', type=int,
                       help='Limit processing to N days (for testing)')
    parser.add_argument('--batch-size', type=int, default=5,
                       help='Number of videos to process per batch')
    
    args = parser.parse_args()
    
    print("⚔️  SWORDFINDER v2 - PHASE 2: VIDEO PROCESSING")
    print("=" * 60)
    
    try:
        processor = TopSwordVideoProcessor()
        
        if args.verify:
            processor.verify_results()
            return
        
        # Get candidates
        candidates = processor.get_top_swords_for_processing(args.limit_days)
        
        if not candidates:
            print("ℹ️  No videos to process. All top swords may already have videos.")
            return
        
        if args.query_only:
            print("📋 QUERY-ONLY MODE: Showing candidates that would be processed")
            for i, candidate in enumerate(candidates[:20], 1):  # Show first 20
                print(f"  #{i}: {candidate.get('game_date', 'Unknown')} - {candidate.get('pitcher_name', 'Unknown')} vs "
                      f"{candidate.get('batter_name', 'Unknown')} (Score: {candidate.get('sword_score', 0)})")
            if len(candidates) > 20:
                print(f"  ... and {len(candidates) - 20} more")
            return
        
        # Process videos
        print(f"🚀 Processing {len(candidates)} sword swing videos...")
        
        if args.limit_days:
            print(f"🧪 TEST MODE: Limited to {args.limit_days} days")
        
        confirm = input(f"\nThis will download and process {len(candidates)} videos. Continue? (y/N): ").strip().lower()
        
        if confirm == 'y':
            start_time = time.time()
            processed, failed = processor.process_video_batch(candidates, args.batch_size)
            end_time = time.time()
            
            duration = end_time - start_time
            print(f"\n⏱️  Total processing time: {duration/60:.1f} minutes")
            if len(candidates) > 0:
                print(f"🚀 Average time per video: {duration/len(candidates):.1f} seconds")
            
            # Verify results
            print("\n" + "="*50)
            processor.verify_results()
            
        else:
            print("❌ Processing cancelled")
    
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 