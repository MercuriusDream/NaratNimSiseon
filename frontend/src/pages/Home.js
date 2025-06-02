import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import SentimentChart from '../components/SentimentChart';

function Home() {
  const [stats, setStats] = useState({
    totalSessions: 0,
    totalBills: 0,
    totalSpeakers: 0,
    totalParties: 0,
  });
  const [recentSessions, setRecentSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, sessionsRes] = await Promise.all([
          axios.get('http://localhost:8000/api/stats/'),
          axios.get('http://localhost:8000/api/sessions/?limit=5')
        ]);
        
        setStats(statsRes.data);
        setRecentSessions(sessionsRes.data.results);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">국회 감성 분석 대시보드</h1>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-600">총 회의 수</h3>
          <p className="text-3xl font-bold text-blue-600">{stats.totalSessions}</p>
          <Link to="/sessions" className="text-blue-500 hover:text-blue-700 text-sm mt-2 inline-block">
            모든 회의 보기 →
          </Link>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-600">총 법안 수</h3>
          <p className="text-3xl font-bold text-green-600">{stats.totalBills}</p>
          <Link to="/bills" className="text-green-500 hover:text-green-700 text-sm mt-2 inline-block">
            모든 법안 보기 →
          </Link>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-600">총 발언자 수</h3>
          <p className="text-3xl font-bold text-purple-600">{stats.totalSpeakers}</p>
          <Link to="/speakers" className="text-purple-500 hover:text-purple-700 text-sm mt-2 inline-block">
            모든 발언자 보기 →
          </Link>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-600">총 정당 수</h3>
          <p className="text-3xl font-bold text-red-600">{stats.totalParties}</p>
          <Link to="/parties" className="text-red-500 hover:text-red-700 text-sm mt-2 inline-block">
            모든 정당 보기 →
          </Link>
        </div>
      </div>

      {/* Recent Sessions */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">최근 회의</h2>
        <div className="space-y-4">
          {recentSessions.map(session => (
            <div key={session.id} className="border-b pb-4 last:border-b-0">
              <Link to={`/sessions/${session.id}`} className="block hover:bg-gray-50 p-2 rounded">
                <h3 className="text-lg font-semibold">{session.title}</h3>
                <p className="text-gray-600">{new Date(session.date).toLocaleDateString()}</p>
              </Link>
            </div>
          ))}
        </div>
      </div>

      {/* Sentiment Analysis Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-4">감성 분석 결과</h2>
        <SentimentChart data={recentSessions} />
      </div>
    </div>
  );
}

export default Home; 