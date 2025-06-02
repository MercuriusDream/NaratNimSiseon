
import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Link } from 'react-router-dom';
import { fetchStats } from '../api';

const Home = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadStats = async () => {
      try {
        setLoading(true);
        const data = await fetchStats();
        setStats(data);
      } catch (err) {
        console.error('Error fetching stats:', err);
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        // Set default stats for demo
        setStats({
          total_parties: 5,
          total_sessions: 150,
          total_bills: 500,
          total_speakers: 300
        });
      } finally {
        setLoading(false);
      }
    };

    loadStats();
  }, []);

  if (loading) {
    return (
      <Layout>
        <div className="container">
          <div className="loading">데이터를 불러오는 중...</div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="container">
        <div className="hero-section">
          <h1>나랏님 시선</h1>
          <p>대한민국 국회의 투명성과 민주주의를 위한 종합 정보 플랫폼</p>
        </div>

        {error && (
          <div className="error">
            {error}
          </div>
        )}

        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-number">{stats?.total_parties || 0}</span>
            <div className="stat-label">정당</div>
            <Link to="/parties" className="view-all-link">
              전체 보기
            </Link>
          </div>

          <div className="stat-card">
            <span className="stat-number">{stats?.total_sessions || 0}</span>
            <div className="stat-label">회의록</div>
            <Link to="/sessions" className="view-all-link">
              전체 보기
            </Link>
          </div>

          <div className="stat-card">
            <span className="stat-number">{stats?.total_bills || 0}</span>
            <div className="stat-label">의안</div>
            <Link to="/bills" className="view-all-link">
              전체 보기
            </Link>
          </div>

          <div className="stat-card">
            <span className="stat-number">{stats?.total_speakers || 0}</span>
            <div className="stat-label">의원</div>
            <Link to="/speakers" className="view-all-link">
              전체 보기
            </Link>
          </div>
        </div>

        <div className="content-section">
          <h2>최근 국정 활동</h2>
          <div className="card">
            <div className="card-content">
              <h3 className="card-title">국회 데이터 분석 시스템</h3>
              <p className="card-description">
                투명하고 접근 가능한 국회 정보를 통해 민주주의의 가치를 실현합니다.
                의안, 회의록, 의원 활동 등 다양한 국정 정보를 한눈에 확인하세요.
              </p>
              <div className="card-meta">
                <span className="badge badge-primary">정보 공개</span>
                <span>업데이트: 매일</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default Home;
