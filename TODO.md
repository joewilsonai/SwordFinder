# ⚔️ SwordFinder TODO - January 2025

## 🚀 CURRENT STATUS (Updated January 2025)

### ✅ Completed & Automated
- [x] Database schema with all 118+ MLB fields
- [x] 353,506 MLB pitches uploaded to Supabase
- [x] Sword scores calculated for all eligible pitches
- [x] Perceived velocity calculations complete
- [x] Strike zone boundaries and distances calculated
- [x] All percentiles calculated and indexed
- [x] Daily update script with duplicate prevention
- [x] GitHub Actions for automated daily updates
- [x] Video processing automated (10 videos daily)
- [x] Spring training filtering (no videos available)
- [x] Azure blob storage integration working
- [x] Play ID mapping fixed for accurate videos

### 🤖 Running Automatically
- **Daily MLB Update**: 1 PM UTC via GitHub Actions
- **Daily Video Processing**: 2 PM UTC via GitHub Actions
- Both workflows tested and operational

## 🎯 IMMEDIATE PRIORITIES

### 1. Build the Web Application

#### Frontend (Vanilla JavaScript + Tailwind CSS)
- [ ] Project setup with vanilla JavaScript
- [ ] Tailwind CSS integration for beautiful, modern styling
- [ ] Video player component with native HTML5 video controls
- [ ] Home page with daily sword highlights
- [ ] Leaderboard page with sortable tables (vanilla JS)
- [ ] Player profile pages with dynamic content
- [ ] Pitcher profile pages (sword inducers)
- [ ] Search functionality with debounced input
- [ ] Mobile responsive design using Tailwind utilities
- [ ] Share buttons for individual swords
- [ ] Progressive enhancement approach
- [ ] Lazy loading for images and videos
- [ ] Simple state management without frameworks

#### Why Vanilla JS + Tailwind?
- No build step required (can use CDN for Tailwind)
- Faster initial load times
- Easier to understand and maintain
- Direct DOM manipulation for dynamic content
- Modern JavaScript (ES6+) is powerful enough
- Tailwind provides utility-first CSS for rapid UI development

#### API Expansion
- [ ] `/swords/date/{date}` - Swords by specific date
- [ ] `/swords/player/{player_id}` - Player sword history
- [ ] `/swords/team/{team}` - Team sword stats
- [ ] `/pitchers/{pitcher_id}/induced` - Pitchers who cause swords
- [ ] `/stats/trends` - Sword trends over time
- [ ] `/leaderboards/all-time` - Historical leaderboards
- [ ] Authentication endpoints
- [ ] Rate limiting middleware

### 2. Performance Optimization
- [ ] Redis caching for expensive queries
- [ ] CDN setup for video delivery
- [ ] Database query optimization
- [ ] API response compression
- [ ] Image optimization for player photos
- [ ] Lazy loading for video lists

### 3. Analytics Dashboard
- [ ] D3.js visualizations for sword distributions
- [ ] Heat maps showing sword zones
- [ ] Team comparison charts
- [ ] Player improvement tracking
- [ ] Pitch sequence analysis
- [ ] Export functionality for data

## 📊 PHASE 2: Advanced Features

### Enhanced Metrics
- [ ] Sword Rate per 100 swings
- [ ] Sword Inducer Rate for pitchers
- [ ] Clutch Sword Index (leverage situations)
- [ ] Recovery Rate (performance after swords)
- [ ] Sword prediction model
- [ ] Swing plane optimization suggestions

### Social Features
- [ ] User accounts and favorites
- [ ] Comment system for videos
- [ ] Sword brackets/tournaments
- [ ] Weekly sword awards
- [ ] Email notifications for favorite players
- [ ] Discord/Slack integrations

### Content Generation
- [ ] Auto-generate social media clips
- [ ] Weekly highlight reels
- [ ] Player comparison videos
- [ ] Educational content about hitting
- [ ] Automated Twitter/X posts
- [ ] Instagram story templates

## 🔧 INFRASTRUCTURE IMPROVEMENTS

### Monitoring & Reliability
- [ ] Sentry error tracking
- [ ] Datadog performance monitoring
- [ ] Uptime monitoring
- [ ] Database backup automation
- [ ] Disaster recovery plan
- [ ] Load testing

### Deployment
- [ ] Docker containers
- [ ] Kubernetes deployment
- [ ] CI/CD pipeline improvements
- [ ] Staging environment
- [ ] Blue-green deployments
- [ ] SSL and domain setup

### Data Pipeline
- [ ] Parallel video processing
- [ ] Webhook for real-time updates
- [ ] Historical data backfill (2024)
- [ ] Minor league data integration
- [ ] Statcast 3D data integration

## 📱 MOBILE & PLATFORM EXPANSION

### Mobile App
- [ ] Progressive Web App (PWA) using vanilla JS
- [ ] Service workers for offline functionality
- [ ] Web app manifest for installability
- [ ] Push notifications via Web Push API
- [ ] Responsive design that works great on mobile
- [ ] Native app using WebView wrapper if needed

### Platform Integrations
- [ ] MLB official partnership
- [ ] Fantasy baseball integrations
- [ ] Broadcast overlays
- [ ] Team partnerships
- [ ] Media API access

## 🐛 KNOWN ISSUES & IMPROVEMENTS

### Data Quality
- [x] ~~Some "swinging strikes" show no swing~~ (Filtered in queries)
- [x] ~~Spring training videos unavailable~~ (Now filtered automatically)
- [ ] Strike zones use league average (not player-specific)

### Performance
- [x] ~~Perceived velocity calculation slow~~ (Completed)
- [x] ~~Duplicate entries in daily updates~~ (Fixed with smart filtering)
- [ ] Video processing could be parallelized
- [ ] Large CSV files in repo (consider Git LFS)

### Features
- [ ] Multi-angle video views
- [ ] Slow motion analysis
- [ ] Swing comparison tools
- [ ] Coaching feedback system

## 📅 REALISTIC TIMELINE

### Week 1-2 (Current)
- [ ] Basic frontend with video player
- [ ] Essential API endpoints
- [ ] Deploy to production

### Week 3-4
- [ ] Complete UI features
- [ ] Performance optimization
- [ ] User testing

### Month 2
- [ ] Advanced analytics
- [ ] Social features
- [ ] Mobile app development

### Month 3
- [ ] Platform integrations
- [ ] Marketing launch
- [ ] Partnership discussions

## 🎯 SUCCESS METRICS

### Technical
- API response time < 200ms (p95)
- Video load time < 2 seconds
- 99.9% uptime
- Zero data loss

### User Engagement
- 1,000 daily active users
- 5+ minute average session
- 20% weekly retention
- 50+ media mentions

### Business
- 5 team partnerships
- 10,000 video views/week
- Positive ROI within 6 months
- MLB official recognition

## 💡 FUTURE IDEAS

### Premium Features
- [ ] Custom alerts for specific criteria
- [ ] Advanced analytics API
- [ ] White-label for teams
- [ ] Coaching consultation booking
- [ ] NFT sword moments

### Research Projects
- [ ] ML model for swing improvement
- [ ] Biomechanics analysis
- [ ] Injury prediction from swing data
- [ ] Optimal swing path calculator
- [ ] VR training integration

### Community
- [ ] Sword swing contests
- [ ] Player AMAs
- [ ] User-submitted nominations
- [ ] Coaching clinics
- [ ] Youth baseball integration

---

**Last Updated**: January 2025  
**Status**: Core infrastructure complete and automated, ready for UI development  
**Priority**: Build the web application to showcase the data

Use `ui/assets/config.js` for public runtime UI configuration.
