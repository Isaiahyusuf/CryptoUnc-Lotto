# CryptoUnc Lotto - 3D Interactive Website

A cutting-edge 3D web experience for the CryptoUnc Lotto Telegram bot. Buy lottery tickets, track winnings, earn free tickets through referrals, and compete on global leaderboards—all with stunning 3D visuals and blockchain transparency.

## 🎮 Features

### Core Gameplay
- **3D Lottery Visualization** - Watch animated lottery balls draw in real-time with Three.js
- **Live Ticket Purchase** - Buy tickets directly from the web (SOL payments via Phantom Wallet)
- **Tiered Prize System** - Win prizes based on matched numbers:
  - 🏆 5 Matches: 70% of jackpot
  - 🥈 4 Matches: 20% of jackpot
  - 🥉 3 Matches: 10% of jackpot

### Referral System
- **Share & Earn** - Invite friends and earn FREE TICKETS
- **2-Referral Rewards** - Every 2 successful referrals = 1 free ticket
- **Unlimited Growth** - Rewards repeat infinitely as you build your network
- **Real-Time Tracking** - Monitor your referral stats and free tickets

### User Features
- **My Stats Dashboard** - Total spent, winnings, VIP tier progress, referral earnings
- **Live Leaderboard** - Top players and biggest winners with filters
- **Round History** - See past draws, winning numbers, and prize distributions
- **Wallet Integration** - Connect Phantom wallet for seamless SOL transactions
- **VIP Tiers** - Bronze → Silver → Gold → Platinum → Diamond based on tickets purchased

### Transparency
- **Blockchain Verification** - All transactions on Solana with Solscan links
- **Provably Fair** - Random number generation verified on-chain
- **Prize Pool Tracking** - Real-time jackpot updates from owner wallet
- **Rollover Tracking** - See unclaimed prize rollovers between rounds

## 🏗️ Tech Stack

### Frontend
- **React 18** - Modern UI framework
- **Vite** - Lightning-fast build tool
- **Three.js** - 3D graphics engine for lottery visualization
- **React Router** - Client-side routing
- **Tailwind CSS** - Responsive utility-first styling
- **Framer Motion** - Smooth animations and transitions
- **Phantom Wallet Integration** - Solana wallet connection

### Backend
- **Python 3.11** - Telegram bot + API server
- **aiogram** - Telegram bot framework
- **Solana SDK** - Blockchain interaction
- **PostgreSQL** - User data & lottery records
- **FastAPI** - REST API for web frontend

### Blockchain
- **Solana** - Layer 1 blockchain
- **Phantom Wallet** - User wallet integration
- **Solscan** - Transaction verification

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn
- Phantom Wallet browser extension
- SOL tokens on Solana devnet/mainnet

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd cryptounc-lotto-web

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env.local
# Edit .env.local with your bot API endpoint

# Start development server
npm run dev
```

The site will be available at `http://localhost:5000`

### Build for Production

```bash
npm run build
npm run preview
```

## 📁 Project Structure

```
cryptounc-lotto-web/
├── public/                    # Static assets
│   ├── sounds/               # Lottery draw sounds, notifications
│   └── models/               # 3D models for lottery balls
├── src/
│   ├── components/           # React components
│   │   ├── Navigation.jsx    # Top navigation bar
│   │   ├── LotteryVisual.jsx # 3D lottery scene
│   │   ├── TicketBuyer.jsx   # Ticket purchase flow
│   │   ├── Leaderboard.jsx   # Players ranking
│   │   └── ...
│   ├── pages/                # Page components (route-based)
│   │   ├── Home.jsx          # Hero + game info
│   │   ├── Play.jsx          # Ticket purchase page
│   │   ├── Results.jsx       # Draw results history
│   │   ├── Stats.jsx         # User statistics
│   │   ├── Referrals.jsx     # Referral dashboard
│   │   └── About.jsx         # How it works
│   ├── hooks/                # Custom React hooks
│   │   ├── useWallet.js      # Phantom wallet connection
│   │   ├── useRounds.js      # Lottery rounds API
│   │   └── useUser.js        # User data API
│   ├── api/                  # API integration
│   │   └── botApi.js         # Bot backend endpoints
│   ├── 3d/                   # Three.js scenes
│   │   ├── LotteryScene.js   # Lottery ball drawing
│   │   ├── ParticleEffects.js# Win/loss effects
│   │   └── Models.js         # 3D model loading
│   ├── styles/               # Global styles
│   │   └── globals.css       # Tailwind + custom CSS
│   ├── App.jsx               # Main app component
│   └── main.jsx              # React entry point
├── .env.example              # Environment template
├── package.json              # Dependencies
├── vite.config.js            # Vite configuration
└── tailwind.config.js        # Tailwind CSS configuration
```

## 🎯 Page Features

### Home Page
- Hero section with dynamic 3D background
- Game mechanics overview
- Quick start button
- Featured leaderboard highlights
- Referral CTA with reward info

### Play Page
- Number selector (1-40, pick 5)
- Ticket price display
- Wallet connection status
- Buy button with transaction status
- Recent round stats
- Free tickets indicator

### Results Page
- Past 10 rounds with results
- Winning numbers display
- Prize tier information
- Winner announcements
- Rollover tracking

### Stats Page
- User profile info
- VIP tier progress
- Total spent / won statistics
- Win rate analytics
- Biggest win trophy
- Referral stats (friends, earnings, free tickets)

### Leaderboard Page
- Top 100 players by tickets purchased
- Top 100 winners by prize amount
- Filters: timeframe (all-time, monthly, weekly)
- User rank highlighting
- Search player by username

### Referrals Page
- Your unique referral link
- Share buttons (Telegram, Twitter, Copy)
- Referral stats dashboard
- Free tickets earned counter
- Referral history with timestamps
- Instructions for earning more

### About Page
- How to play tutorial
- Tier system explanation
- Referral system details
- Blockchain transparency info
- FAQ section
- Support contact

## 🔌 API Integration

The website connects to the bot backend API:

```javascript
// Examples
GET  /api/rounds/active          # Get current round
GET  /api/rounds/{id}/results    # Get round results
POST /api/tickets/buy            # Purchase ticket
GET  /api/user/stats             # User statistics
GET  /api/user/referrals         # Referral data
GET  /api/leaderboard/players    # Top players
GET  /api/leaderboard/winners    # Top winners
```

## 🎨 3D Features

### Lottery Ball Animation
- Realistic sphere physics
- Particle effects on draw
- Camera tracking animation
- Sound effects synchronization
- Victory/defeat screen variations

### Background Effects
- Animated gradient mesh
- Floating crypto symbols
- Responsive to user interaction
- Performance optimized

### Win/Loss Animations
- Confetti burst on wins
- Shake effect on loss
- Prize amount reveal animation
- Tier-specific visual effects

## 💳 Wallet Integration

Using Phantom Wallet for secure Solana transactions:

```javascript
// User connects wallet
const provider = window.phantom?.solana;
const wallet = await provider.connect();

// Purchase ticket
const transaction = await buyTicket(ticketData);
const signature = await provider.signAndSendTransaction(transaction);
```

Supports:
- Devnet (testing)
- Testnet (staging)
- Mainnet (production)

## 📊 Real-Time Features

- Live round countdown timer
- Player count updates
- Jackpot amount refresh
- Result notifications
- Leaderboard live updates

## 🔒 Security

- Wallet private keys never stored
- All transactions verified on-chain
- User data encrypted in transit
- Rate limiting on API requests
- CSRF protection
- XSS prevention

## 📱 Responsive Design

- Mobile-first approach
- Optimized for all screen sizes
- Touch-friendly interactions
- 3D scenes adapt to viewport
- Performance optimized for mobile

## 🌍 Deployment

### Vercel (Recommended)
```bash
npm install -g vercel
vercel
```

### Netlify
```bash
npm install -g netlify-cli
netlify deploy
```

### Docker
```bash
docker build -t cryptounc-lotto-web .
docker run -p 5000:5000 cryptounc-lotto-web
```

## 🛠️ Development

### Environment Variables

```env
VITE_BOT_API_URL=http://localhost:8000
VITE_SOLANA_NETWORK=devnet
VITE_PHANTOM_APP_ID=your-app-id
```

### Scripts

```bash
npm run dev          # Start dev server
npm run build        # Build for production
npm run preview      # Preview build locally
npm run lint         # Check code quality
```

## 🐛 Debugging

Enable debug mode:

```bash
VITE_DEBUG=true npm run dev
```

Browser console will show:
- API calls
- Wallet interactions
- 3D scene performance
- Lottery calculations

## 📈 Performance

- Lighthouse score: 95+
- First contentful paint: < 1.5s
- Time to interactive: < 3s
- 3D scene FPS: 60fps target

Optimizations:
- Code splitting per page
- Lazy loading components
- 3D model compression
- Image optimization
- Service worker caching

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🎯 Roadmap

- [ ] Mobile app (React Native)
- [ ] Voice announcements (audio playback)
- [ ] Advanced analytics dashboard
- [ ] Custom theme selector
- [ ] Multiplayer lottery mode
- [ ] Prize pool insurance
- [ ] DAO governance integration
- [ ] NFT ticket receipts
- [ ] Cross-chain expansion (Ethereum, Polygon)
- [ ] Affiliate marketing tools

## 🆘 Support

- **Documentation**: [Full guide](./docs)
- **Telegram**: @CryptoUncLottoSupport
- **Discord**: [Community server](https://discord.gg/cryptounc)
- **Email**: support@cryptounc.io
- **Issues**: [GitHub issues](https://github.com/cryptounc/lotto-web/issues)

## ⭐ Community

- Star ⭐ this repo if you find it useful
- Follow on Twitter [@CryptoUncLotto](https://twitter.com/cryptounclotto)
- Join our Telegram community [@CryptoUncLotto](https://t.me/cryptounclotto)
- Share your referral link with friends

---

**Built with ❤️ for the Web3 gaming community**

*Play fair. Win big. Share rewards.*
