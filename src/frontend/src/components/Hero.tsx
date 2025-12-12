import { useState, FormEvent } from 'react';
import { Github, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

interface HeroProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
}

export const Hero = ({ onSubmit, isLoading }: HeroProps) => {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  const validateUrl = (url: string): boolean => {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname === 'github.com' || urlObj.hostname.includes('github.com');
    } catch {
      return false;
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (!url.trim()) {
      setError('Please enter a GitHub repository URL');
      return;
    }

    if (!validateUrl(url)) {
      setError('Please enter a valid GitHub repository URL');
      return;
    }

    onSubmit(url.trim());
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-2xl mx-auto"
    >
      <div className="text-center mb-8">
        <h1 className="text-5xl font-bold mb-4" style={{ color: '#222222' }}>
          AutoRead<span style={{ color: '#FF6D1F' }}>ME</span>
        </h1>
        <p className="text-lg" style={{ color: '#222222', opacity: 0.7 }}>
          Automatically generate beautiful documentation for your GitHub repositories
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <Github className="h-5 w-5" style={{ color: '#666666' }} />
          </div>
          <input
            type="text"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setError('');
            }}
            placeholder="https://github.com/username/repository"
            className="w-full pl-12 pr-4 py-4 rounded-lg focus:outline-none focus:ring-2 focus:border-transparent transition-all"
            style={{
              backgroundColor: '#FFFFFF',
              border: '1px solid #222222',
              color: '#222222',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#FF6D1F';
              e.target.style.boxShadow = '0 0 0 2px rgba(255, 109, 31, 0.2)';
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#222222';
              e.target.style.boxShadow = 'none';
            }}
            disabled={isLoading}
          />
        </div>

        {error && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-sm"
            style={{ color: '#EF4444' }}
          >
            {error}
          </motion.p>
        )}

        <motion.button
          type="submit"
          disabled={isLoading}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="w-full py-4 disabled:cursor-not-allowed text-white font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors"
          style={{
            backgroundColor: isLoading ? '#999999' : '#FF6D1F',
          }}
        >
          {isLoading ? (
            <>
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Processing...</span>
            </>
          ) : (
            <>
              <span>Generate Documentation</span>
              <ArrowRight className="w-5 h-5" />
            </>
          )}
        </motion.button>
      </form>
    </motion.div>
  );
};

