import React from 'react';
import { Link } from 'react-router-dom';

const Layout = ({ children }) => {
  return (
    <div className="App">
      <header className="header">
        <div className="nav-container">
          <Link to="/" className="logo">
            나랏님 시선
          </Link>
          <nav className="nav-links">
            <Link to="/" className="nav-link">홈</Link>
            <Link to="/parties" className="nav-link">정당 목록</Link>
            <Link to="/sessions" className="nav-link">회의록 목록</Link>
            <Link to="/bills" className="nav-link">의안 목록</Link>
            <Link to="/speakers" className="nav-link">의원 목록</Link>
          </nav>
        </div>
      </header>
      <main>
        {children}
      </main>
      <footer style={{
        background: '#1e293b',
        color: 'white',
        textAlign: 'center',
        padding: '2rem',
        marginTop: '4rem'
      }}>
        <p>&copy; 2024 나랏님 시선. 모든 권리 보유.</p>
      </footer>
    </div>
  );
};

export default Layout;