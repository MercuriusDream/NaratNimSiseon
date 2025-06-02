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
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const MAX_RETRIES = 3;

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const [statsRes, sessionsRes] = await Promise.all([
          axios.get('http://localhost:8000/api/stats/'),
          axios.get('http://localhost:8000/api/sessions/?limit=5')
        ]);
        
        setStats(statsRes.data);
        setRecentSessions(sessionsRes.data.results);
        setRetryCount(0); // Reset retry count on success
      } catch (error) {
        console.error('Error fetching data:', error);
        if (retryCount < MAX_RETRIES) {
          setRetryCount(prev => prev + 1);
          setTimeout(fetchData, 1000 * Math.pow(2, retryCount)); // Exponential backoff
        } else {
          setError(error.response?.data?.message || '데이터를 불러오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [retryCount]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center p-4">
        <div className="text-red-600 mb-4">{error}</div>
        {retryCount < MAX_RETRIES && (
          <button
            onClick={() => setRetryCount(prev => prev + 1)}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            다시 시도
          </button>
        )}
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
          <p className="text-3xl font-bold text-orange-600">{stats.totalParties}</p>
          <Link to="/parties" className="text-orange-500 hover:text-orange-700 text-sm mt-2 inline-block">
            모든 정당 보기 →
          </Link>
        </div>
      </div>

      {/* Recent Sessions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-4">최근 회의</h2>
        {recentSessions.length > 0 ? (
          <div className="space-y-4">
            {recentSessions.map(session => (
              <Link
                key={session.id}
                to={`/sessions/${session.id}`}
                className="block p-4 border rounded-lg hover:bg-gray-50"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">{session.conf_knd}</h3>
                    <p className="text-gray-600">
                      {new Date(session.conf_dt).toLocaleDateString()} {session.bg_ptm}
                    </p>
                  </div>
                  <div className="text-blue-600">→</div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-gray-600">최근 회의가 없습니다.</p>
        )}
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