import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import SessionCard from '../components/SessionCard';

const SessionList = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({});
  const [currentPage, setCurrentPage] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    fetchSessions();
  }, [currentPage]);

  const fetchSessions = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: currentPage
      });

      const response = await api.get(`/api/sessions/?${params}`);
      setSessions(response.data.results || response.data);
      setPagination({
        count: response.data.count,
        next: response.data.next,
        previous: response.data.previous
      });
    } catch (err) {
      setError('세션 목록을 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching sessions:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <NavigationHeader />
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">국회 회의 목록</h1>

        {loading && <p>Loading sessions...</p>}
        {error && <p>Error: {error}</p>}
        {sessions && sessions.map(session => (
          <div key={session.conf_id} className="border p-4 mb-4 rounded-lg cursor-pointer hover:shadow-md" onClick={() => navigate(`/sessions/${session.conf_id}`)}>
            <h3 className="font-semibold text-lg mb-2">{session.era_co} {session.sess} {session.dgr}</h3>
            <p className="text-gray-600 mb-2">회의일: {session.conf_dt}</p>
            <p className="text-gray-600">회의번호: {session.conf_id}</p>
          </div>
        ))}

        {/* Pagination */}
        {pagination.count > 10 && (
          <div className="flex justify-center space-x-2 mt-8">
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={!pagination.previous}
              className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              이전
            </button>
            <span className="px-4 py-2 text-gray-700">
              페이지 {currentPage} / {Math.ceil(pagination.count / 10)}
            </span>
            <button
              onClick={() => setCurrentPage(prev => prev + 1)}
              disabled={!pagination.next}
              className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              다음
            </button>
          </div>
        )}
      </div>
      <Footer />
    </div>
  );
};

export default SessionList;