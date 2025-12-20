import { motion } from 'framer-motion'
import { ArrowRight, Dice5, Users, Trophy, Zap } from '@phosphor-icons/react'
import LotteryBackground from '../3d/LotteryBackground'

export default function Home() {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.2, delayChildren: 0.3 }
    }
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.8 } }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-dark via-darker to-dark overflow-hidden">
      <LotteryBackground />

      {/* Hero Section */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
        className="container-custom pt-32 pb-20"
      >
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="text-center"
        >
          {/* Badge */}
          <motion.div variants={itemVariants} className="mb-8 inline-block">
            <div className="glass px-6 py-3 rounded-full text-indigo-300 flex items-center gap-2">
              <Zap size={16} weight="fill" />
              <span className="text-sm font-semibold">Live on Solana Blockchain</span>
            </div>
          </motion.div>

          {/* Main Heading */}
          <motion.h1
            variants={itemVariants}
            className="text-6xl md:text-7xl font-black mb-6 leading-tight"
          >
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400">
              3D Blockchain Lottery
            </span>
            <br />
            <span className="text-gray-300">Win Big, Fair & Transparent</span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p
            variants={itemVariants}
            className="text-xl text-gray-400 mb-12 max-w-2xl mx-auto"
          >
            Experience the future of gaming. Buy tickets, match numbers, win real SOL. Transparent, provably fair, powered by blockchain.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            variants={itemVariants}
            className="flex flex-col sm:flex-row gap-4 justify-center mb-20"
          >
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="btn-primary flex items-center justify-center gap-2"
            >
              Play Now
              <ArrowRight size={20} weight="bold" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="btn-secondary flex items-center justify-center gap-2"
            >
              Learn More
            </motion.button>
          </motion.div>

          {/* Stats */}
          <motion.div
            variants={itemVariants}
            className="grid grid-cols-3 gap-4 max-w-2xl mx-auto"
          >
            {[
              { label: 'Total Prize Pool', value: '150+ SOL' },
              { label: 'Active Players', value: '5,000+' },
              { label: 'Total Paid Out', value: '2,500 SOL' }
            ].map((stat, i) => (
              <div key={i} className="glass rounded-lg p-4">
                <p className="text-gray-400 text-sm mb-1">{stat.label}</p>
                <p className="text-2xl font-bold text-indigo-400">{stat.value}</p>
              </div>
            ))}
          </motion.div>
        </motion.div>
      </motion.section>

      {/* Features Section */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
        className="container-custom py-20"
      >
        <h2 className="text-4xl font-bold text-center mb-4 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
          Why CryptoUnc Lotto?
        </h2>
        <p className="text-center text-gray-400 mb-16 max-w-2xl mx-auto">
          The most transparent, fair, and rewarding lottery experience on Solana
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            {
              icon: Trophy,
              title: '3D Visualizations',
              description: 'Watch lottery balls draw in stunning 3D with real-time animations'
            },
            {
              icon: Dice5,
              title: 'Tiered Prizes',
              description: 'Match 3, 4, or 5 numbers. More matches = bigger rewards'
            },
            {
              icon: Users,
              title: 'Referral Rewards',
              description: 'Invite friends, earn free tickets. Every 2 referrals = 1 free ticket'
            },
            {
              icon: Zap,
              title: 'Instant Payouts',
              description: 'Winners receive SOL instantly to their wallet on-chain'
            }
          ].map((feature, i) => {
            const Icon = feature.icon
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1, duration: 0.6 }}
                viewport={{ once: true }}
                whileHover={{ y: -10 }}
                className="glass rounded-lg p-8 group hover:border-indigo-500 transition-all duration-300"
              >
                <Icon size={40} weight="duotone" className="text-indigo-400 mb-4 group-hover:text-purple-400 transition-colors" />
                <h3 className="text-xl font-bold mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-sm leading-relaxed">{feature.description}</p>
              </motion.div>
            )
          })}
        </div>
      </motion.section>

      {/* How It Works */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
        className="container-custom py-20"
      >
        <h2 className="text-4xl font-bold text-center mb-16 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
          How It Works
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {[
            { step: '1', title: 'Connect Wallet', desc: 'Link your Phantom wallet' },
            { step: '2', title: 'Buy Tickets', desc: 'Choose 5 numbers (1-40)' },
            { step: '3', title: 'Wait for Draw', desc: 'Hourly draws every hour' },
            { step: '4', title: 'Win & Claim', desc: 'Instant SOL to your wallet' }
          ].map((item, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.8 }}
              whileInView={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.15, duration: 0.6 }}
              viewport={{ once: true }}
              className="relative"
            >
              {/* Step circle */}
              <div className="w-16 h-16 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 flex items-center justify-center mb-6 mx-auto relative z-10">
                <span className="text-2xl font-bold">{item.step}</span>
              </div>

              {/* Connector line */}
              {i < 3 && (
                <div className="hidden md:block absolute top-8 left-[60%] w-[calc(100%-20px)] h-1 bg-gradient-to-r from-indigo-500 to-transparent" />
              )}

              {/* Content */}
              <div className="glass rounded-lg p-6 text-center">
                <h3 className="font-bold text-lg mb-2">{item.title}</h3>
                <p className="text-gray-400 text-sm">{item.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.section>

      {/* Prize Structure */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
        className="container-custom py-20"
      >
        <h2 className="text-4xl font-bold text-center mb-4 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
          Prize Distribution
        </h2>
        <p className="text-center text-gray-400 mb-16 max-w-2xl mx-auto">
          Win based on how many numbers you match
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { title: '5-Match JACKPOT', emoji: '🏆', percentage: '70%', desc: 'Full jackpot winner' },
            { title: '4-Match Winner', emoji: '🥈', percentage: '20%', desc: 'Silver prize tier' },
            { title: '3-Match Winner', emoji: '🥉', percentage: '10%', desc: 'Bronze prize tier' }
          ].map((prize, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1, duration: 0.6 }}
              viewport={{ once: true }}
              whileHover={{ scale: 1.05 }}
              className="glass rounded-lg p-8 text-center hover:border-indigo-500 transition-all duration-300 cursor-pointer"
            >
              <div className="text-5xl mb-4">{prize.emoji}</div>
              <h3 className="text-2xl font-bold mb-2">{prize.title}</h3>
              <p className="text-4xl font-black text-indigo-400 mb-2">{prize.percentage}</p>
              <p className="text-gray-400">{prize.desc}</p>
            </motion.div>
          ))}
        </div>
      </motion.section>

      {/* Referral CTA */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
        className="container-custom py-20"
      >
        <motion.div
          whileHover={{ scale: 1.02 }}
          className="glass rounded-2xl p-12 text-center border-2 border-indigo-500/50"
        >
          <h2 className="text-3xl font-bold mb-4">Earn Free Tickets</h2>
          <p className="text-gray-400 mb-8 text-lg">
            Invite friends and earn free tickets instantly. Every 2 successful referrals = 1 FREE TICKET
          </p>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="btn-primary inline-flex items-center gap-2"
          >
            Get Your Referral Link
            <ArrowRight size={20} />
          </motion.button>
        </motion.div>
      </motion.section>

      {/* Footer CTA */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
        className="container-custom py-20 text-center"
      >
        <h2 className="text-5xl font-bold mb-8 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
          Ready to Win?
        </h2>
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          className="btn-primary text-lg px-12 py-4"
        >
          Launch App Now
        </motion.button>
        <p className="text-gray-500 mt-8">24/7 Draws • Transparent • Fair • Instant Payouts</p>
      </motion.section>
    </div>
  )
}
