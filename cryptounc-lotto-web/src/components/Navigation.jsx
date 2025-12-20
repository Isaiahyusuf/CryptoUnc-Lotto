import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { Wallet, Sparkles } from '@phosphor-icons/react'

export default function Navigation() {
  return (
    <motion.nav 
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6 }}
      className="fixed top-0 left-0 right-0 z-50"
    >
      <div className="container-custom py-4">
        <div className="glass rounded-full px-6 py-3 flex items-center justify-between">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-10 h-10 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 flex items-center justify-center">
              <Sparkles weight="bold" size={24} className="text-white group-hover:animate-spin" />
            </div>
            <span className="font-bold text-lg text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
              CryptoUnc Lotto
            </span>
          </Link>

          {/* Right section */}
          <div className="flex items-center gap-4">
            <button className="flex items-center gap-2 px-4 py-2 hover:bg-indigo-500/20 rounded-lg transition-all duration-300">
              <Wallet size={20} />
              <span className="text-sm font-medium">Connect</span>
            </button>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="btn-primary text-sm"
            >
              Play Now
            </motion.button>
          </div>
        </div>
      </div>
    </motion.nav>
  )
}
