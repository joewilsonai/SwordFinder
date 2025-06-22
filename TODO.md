# �� SwordFinder TODO - June 22, 2024 Update

## 🔥 CURRENT STATUS (Updated June 22, 2024, 4:00 PM)

### ⏳ In Progress (Running in Background)
- **Perceived Velocity Calculation**: 20,673 / 353,506 (5.8%) - ETA: ~10-12 hours
- **Strike Zone Boundaries**: 477 / 353,506 (0.1%) - Just started
- **Strike Zone Distance**: Waiting for boundaries to complete

### ✅ Completed
- [x] Database schema with all enhanced columns
- [x] 353,506 MLB pitches uploaded to Supabase
- [x] Sword scores calculated for 338,170 pitches
- [x] 426 videos processed and uploaded to Azure
- [x] API structure created with health and recent swords endpoints
- [x] Daily update script with all calculations integrated
- [x] Play ID mapping fixed for accurate video retrieval

## 🚀 IMMEDIATE NEXT STEPS (When calculations complete)

### 1. Complete Data Population
- [ ] Monitor `perceived_velocity.log` until complete (~10-12 hours)
- [ ] Monitor `sz_bounds.log` until complete (~2-3 hours)
- [ ] Run `python calculate_strike_zone_distance.py` once boundaries are set
- [ ] Run `python calculate_percentiles_sql.py` to populate all percentiles
- [ ] Verify all calculations completed successfully

### 2. Data Validation
- [ ] Query database to verify no unexpected nulls
- [ ] Check percentiles are between 0-100
- [ ] Verify sword scores distribution makes sense
- [ ] Cross-check video URLs with Azure blob storage

### 3. Test Daily Updates
- [ ] Run `python daily_update.py` manually
- [ ] Verify it handles all new calculations correctly
- [ ] Check for any duplicate entries
- [ ] Confirm percentiles update properly

## 🏗️ Build the Web App (Ready to Start!)

### 4. Expand API Endpoints
- [x] ~~`/health` - Basic health check~~ ✅ DONE
- [x] ~~`/swords/recent` - Recent swords with videos~~ ✅ DONE  
- [ ] `/swords/top/{date}` - Top swords by specific date
- [ ] `/swords/search` - Search by player, team, or criteria
- [ ] `/players/{player_id}/swords` - Player sword history
- [ ] `/pitchers/{pitcher_id}/victims` - Pitchers who induce swords
- [ ] `/stats/overview` - Overall statistics and trends
- [ ] `/stats/percentiles` - Distribution data for UI charts
- [ ] `/leaderboards/{metric}` - Various leaderboards (bat speed, extension, etc.)

### 5. Frontend Development
- [ ] Choose framework (Next.js recommended for SEO and performance)
- [ ] Video player component with Azure blob integration
- [ ] Sword leaderboard with filters and sorting
- [ ] Search functionality with autocomplete
- [ ] Player/pitcher profile pages
- [ ] Daily/weekly highlight reels
- [ ] Mobile-responsive design
- [ ] Share functionality for individual swords

### 6. Performance & Optimization
- [ ] Implement Redis caching for expensive queries
- [ ] Add CDN for video delivery
- [ ] Database query optimization
- [ ] API response time monitoring
- [ ] Implement pagination for large result sets

## 📊 Advanced Analytics (Phase 2)

### 7. New Metrics to Calculate
- [ ] "Sword Rate" by player (swords per 100 swings)
- [ ] "Sword Inducer Rate" for pitchers
- [ ] Team-level sword analytics
- [ ] Situational sword rates (by count, inning, score)
- [ ] Sword severity index (combining multiple factors)
- [ ] "Recovery Rate" - players who improve after swords

### 8. Visualizations
- [ ] D3.js charts for sword distributions
- [ ] Heat maps of sword zones
- [ ] Player trend lines over time
- [ ] Interactive pitch sequence viewers
- [ ] 3D swing path visualizations (using bat tracking data)

### 9. Machine Learning Opportunities
- [ ] Predict sword probability pre-pitch
- [ ] Identify swing patterns leading to swords
- [ ] Player improvement recommendations
- [ ] Pitch sequence optimization to avoid swords

## 🔧 Infrastructure & DevOps

### 10. Deployment Setup
- [ ] Dockerize the application
- [ ] Set up CI/CD pipeline
- [ ] Configure production environment
- [ ] SSL certificates and domain setup
- [ ] Monitoring and alerting (Datadog/New Relic)

### 11. Data Pipeline Improvements
- [ ] Optimize video processing pipeline
- [ ] Implement parallel processing for calculations
- [ ] Add data quality checks
- [ ] Backup and disaster recovery plan

## 📱 Mobile & Social Features

### 12. Mobile App
- [ ] React Native app development
- [ ] Push notifications for favorite players
- [ ] Offline video caching
- [ ] Social sharing integration

### 13. Social Media Integration
- [ ] Auto-post daily top swords to Twitter/X
- [ ] Instagram story generator for sword highlights
- [ ] Discord/Slack webhooks for team-specific swords
- [ ] TikTok-style vertical video clips

## 🎯 Known Issues to Address

1. **Data Gaps**
   - ~40% of swings missing play IDs
   - ~56% of pitches missing bat tracking data
   - Spring training games have no video coverage

2. **Performance Issues**
   - Perceived velocity calculation takes ~10-12 hours for full dataset
   - Need to optimize batch processing
   - Video downloads can timeout on slow connections

3. **Data Quality**
   - Some "swinging strikes" show no swing in bat tracking
   - Need better filtering for true sword swings
   - Strike zone boundaries using MLB averages (not player-specific)

## 💡 Future Enhancements

### Premium Features
- [ ] Custom alerts for specific players/teams
- [ ] Advanced analytics dashboard
- [ ] Historical data access (pre-2025)
- [ ] API access for developers
- [ ] White-label solution for teams

### Content & Community
- [ ] User-submitted sword nominations
- [ ] Sword swing contests/brackets
- [ ] Player AMAs about their worst swings
- [ ] Educational content about hitting mechanics

### Partnerships
- [ ] MLB official partnership
- [ ] Team-specific integrations
- [ ] Broadcasting integration
- [ ] Fantasy baseball platforms

## 📅 Realistic Timeline

### Week 1 (Current)
- ✅ Complete all data calculations
- ✅ Basic API structure
- ⏳ Waiting for calculations to finish

### Week 2
- Expand API endpoints
- Basic frontend with video player
- Deploy to staging environment

### Week 3
- Advanced features and analytics
- Performance optimization
- Mobile responsive design

### Week 4
- Polish and bug fixes
- Production deployment
- Marketing and launch

### Ongoing
- Daily data updates
- Feature additions based on feedback
- Performance monitoring and optimization

## 🎯 Success Metrics

### Technical
- API response time < 200ms
- Video load time < 2s
- 99.9% uptime
- < 5 minute data freshness

### Business
- 1,000 DAU within first month
- 10,000 videos viewed/week
- 50+ media mentions
- 5 team partnerships

### Engagement
- Average session > 5 minutes
- 3+ videos watched per session
- 20% weekly return rate
- 1000+ social shares/week

---

**Last Updated**: June 22, 2024, 4:00 PM PST
**Status**: Data calculations in progress, ready for frontend development
**Next Review**: Once calculations complete (~10-12 hours) 