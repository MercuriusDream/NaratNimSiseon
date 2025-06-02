import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function Home() {
  const [stats, setStats] = useState(null);
  const [recentSessions, setRecentSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        const [statsResponse, sessionsResponse] = await Promise.all([
          api.get('/api/stats/'),
          api.get('/api/sessions/?limit=5')
        ]);

        if (mounted) {
          setStats(statsResponse.data);
          setRecentSessions(sessionsResponse.data.results || sessionsResponse.data);
          setLoading(false);
        }
      } catch (error) {
        console.error('Error fetching data:', error);
        if (mounted) {
          setError('데이터를 불러오는데 실패했습니다.');
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <div className="loading">데이터를 불러오는 중...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="container">
      <div className="navigation">
        <div className="nav-links">
          <Link to="/sessions" className="nav-link">회의록</Link>
          <Link to="/bills" className="nav-link">법안</Link>
          <Link to="/speakers" className="nav-link">발언자</Link>
          <Link to="/parties" className="nav-link">정당</Link>
        </div>
      </div>

      <div className="hero-section">
        <h1>국회 감성 분석 대시보드</h1>
        <p>국회 회의록과 발언을 통해 정치적 감성을 분석합니다</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-number">{stats?.total_sessions || 0}</div>
          <div className="stat-label">총 회의 수</div>
          <Link to="/sessions" className="view-all-link">모든 회의 보기 →</Link>
        </div>
        <div className="stat-card">
          <div className="stat-number">{stats?.total_bills || 0}</div>
          <div className="stat-label">총 법안 수</div>
          <Link to="/bills" className="view-all-link">모든 법안 보기 →</Link>
        </div>
        <div className="stat-card">
          <div className="stat-number">{stats?.total_speakers || 0}</div>
          <div className="stat-label">총 발언자 수</div>
          <Link to="/speakers" className="view-all-link">모든 발언자 보기 →</Link>
        </div>
        <div className="stat-card">
          <div className="stat-number">{stats?.total_parties || 0}</div>
          <div className="stat-label">총 정당 수</div>
          <Link to="/parties" className="view-all-link">모든 정당 보기 →</Link>
        </div>
      </div>

      {recentSessions.length > 0 && (
        <div className="recent-section">
          <h2>최근 회의</h2>
          <div className="sessions-list">
            {recentSessions.map(session => (
              <div key={session.id} className="session-card">
                <h3>{session.title}</h3>
                <p>날짜: {session.date}</p>
                <Link to={`/sessions/${session.id}`} className="view-all-link">자세히 보기</Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Home;