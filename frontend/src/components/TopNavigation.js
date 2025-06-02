import React, { useState } from 'react';

const TopNavigation = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-4 bg-white shadow-md">
      <div className="flex items-center space-x-4">
        <img
          src="/logo.png"
          alt="Logo"
          className="w-10 h-10 rounded-full object-cover"
        />
        <h1 className="text-2xl font-bold text-gray-800">의안 목록</h1>
      </div>
      
      {/* Desktop Navigation */}
      <div className="hidden md:flex items-center space-x-8">
        <a href="/" className="text-gray-600 hover:text-gray-900 transition-colors">홈</a>
        <a href="/parties" className="text-gray-600 hover:text-gray-900 transition-colors">정당 목록</a>
        <a href="/meetings" className="text-gray-600 hover:text-gray-900 transition-colors">회의록 목록</a>
        <a href="/bills" className="text-gray-600 hover:text-gray-900 transition-colors">의안 목록</a>
      </div>

      {/* Mobile Menu Button */}
      <button 
        className="md:hidden p-2"
        onClick={toggleMenu}
        aria-label="Toggle menu"
      >
        <svg 
          className="w-6 h-6" 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          {isMenuOpen ? (
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              strokeWidth={2} 
              d="M6 18L18 6M6 6l12 12" 
            />
          ) : (
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              strokeWidth={2} 
              d="M4 6h16M4 12h16M4 18h16" 
            />
          )}
        </svg>
      </button>

      {/* Mobile Navigation */}
      {isMenuOpen && (
        <div className="absolute top-full left-0 right-0 bg-white shadow-md md:hidden">
          <div className="flex flex-col p-4 space-y-4">
            <a 
              href="/" 
              className="text-gray-600 hover:text-gray-900 transition-colors"
              onClick={() => setIsMenuOpen(false)}
            >
              홈
            </a>
            <a 
              href="/parties" 
              className="text-gray-600 hover:text-gray-900 transition-colors"
              onClick={() => setIsMenuOpen(false)}
            >
              정당 목록
            </a>
            <a 
              href="/meetings" 
              className="text-gray-600 hover:text-gray-900 transition-colors"
              onClick={() => setIsMenuOpen(false)}
            >
              회의록 목록
            </a>
            <a 
              href="/bills" 
              className="text-gray-600 hover:text-gray-900 transition-colors"
              onClick={() => setIsMenuOpen(false)}
            >
              의안 목록
            </a>
          </div>
        </div>
      )}
    </nav>
  );
};

export default TopNavigation; 