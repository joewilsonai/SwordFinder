# 🚀 SwordFinder UI Quick Start Guide

**Supabase Project**: Swordfinder  
**Project ID**: seagurfpitfslyxxxztw  
**SQL Editor**: https://app.supabase.com/project/seagurfpitfslyxxxztw/sql/new

## 📋 Pre-UI Checklist (Run These First!)

### 1️⃣ Database Setup (~20 minutes total)
```bash
# Run the interactive setup script
python setup_database_for_ui.py
```

This will guide you through:
- Adding missing database columns
- Calculating perceived velocity (~5 min)
- Calculating strike zone distance (~5 min)
- Calculating all percentiles (~10 min)
- Testing daily updates

### 2️⃣ Install API Dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Test the API
```bash
# Start the API server
uvicorn api:app --reload

# In another terminal, test endpoints:
curl http://localhost:8000/health
curl http://localhost:8000/stats/overview
curl http://localhost:8000/swords/recent
```

## 🎨 Building Your UI

### Option 1: React (Recommended)
```bash
# Create React app
npx create-react-app swordfinder-ui
cd swordfinder-ui

# Install dependencies
npm install axios

# Start development server
npm start
```

Example component:
```jsx
import { useState, useEffect } from 'react';
import axios from 'axios';

function RecentSwords() {
  const [swords, setSwords] = useState([]);
  
  useEffect(() => {
    axios.get('http://localhost:8000/swords/recent')
      .then(res => setSwords(res.data));
  }, []);
  
  return (
    <div>
      {swords.map(sword => (
        <div key={sword.id}>
          <h3>{sword.player_name} - {sword.sword_score.toFixed(1)}</h3>
          <video src={sword.video_azure_blob_url} controls />
        </div>
      ))}
    </div>
  );
}
```

### Option 2: Simple HTML + JavaScript
```html
<!DOCTYPE html>
<html>
<head>
  <title>SwordFinder</title>
</head>
<body>
  <div id="swords"></div>
  
  <script>
    fetch('http://localhost:8000/swords/recent')
      .then(res => res.json())
      .then(swords => {
        const html = swords.map(s => `
          <div>
            <h3>${s.player_name} - Score: ${s.sword_score}</h3>
            <video src="${s.video_azure_blob_url}" controls width="400"></video>
          </div>
        `).join('');
        document.getElementById('swords').innerHTML = html;
      });
  </script>
</body>
</html>
```

## 📊 Available API Endpoints

- `GET /health` - API health check
- `GET /stats/overview` - Database statistics
- `GET /swords/recent?limit=10` - Recent swords with videos
- `GET /swords/worst?limit=20` - All-time worst swords
- `GET /swords/top/{date}` - Top swords for a date
- `GET /players/{player_name}/swords` - Player's sword history
- `GET /search/players?q=query` - Search players

## 🎯 UI Feature Ideas

### Essential Features
- [ ] Video player with controls
- [ ] Sword leaderboard (sortable)
- [ ] Player search
- [ ] Date picker for daily swords
- [ ] Stats dashboard

### Cool Features
- [ ] Side-by-side video comparison
- [ ] Sword score breakdown visualization
- [ ] Player sword timeline
- [ ] Pitch zone visualization
- [ ] Extension vs perceived velocity chart

### Advanced Features
- [ ] Video slow-motion controls
- [ ] Share sword clips
- [ ] Player vs player comparisons
- [ ] Team sword rankings
- [ ] Live updates during games

## 🔧 Environment Variables

Create `.env` in your UI project:
```env
REACT_APP_API_URL=http://localhost:8000
```

## 🚨 Common Issues

1. **CORS Error**: Make sure API is running with CORS enabled
2. **No Videos**: Check Azure blob URLs are accessible
3. **Empty Results**: Run data population scripts first
4. **Slow Queries**: Add database indexes (already in SQL)

## 🎉 Next Steps

1. Start with displaying recent swords
2. Add video player functionality
3. Implement search and filters
4. Add visualizations
5. Deploy to production!

---

**Need help?** The API is self-documenting at http://localhost:8000/docs 