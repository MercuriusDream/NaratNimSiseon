import React, { useState, useEffect } from 'react';
import api from '../api';
import { Link } from 'react-router-dom';

function SpeakerList() {
  const [speakers, setSpeakers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [filters, setFilters] = useState({
    name: '',
    party: '',
    constituency: '',
    era_co: ''
  });

  useEffect(() => {
    fetchSpeakers();
  }, [page, filters]);

  const fetchSpeakers = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page,
        ...filters
      });
      const response = await api.get(`/speakers/?${params}`);
      setSpeakers(response.data.results);
      setTotalPages(Math.ceil(response.data.count / 10));
    } catch (err) {
      setError('데이터를 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching speakers:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setFilters(prev => ({
      ...prev,
      [name]: value
    }));
    setPage(1);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center text-red-600 p-4">
        {error}
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">국회의원 목록</h1>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-xl font-semibold mb-4">검색 필터</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">이름</label>
            <input
              type="text"
              name="name"
              value={filters.name}
              onChange={handleFilterChange}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="이름 검색"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">정당</label>
            <input
              type="text"
              name="party"
              value={filters.party}
              onChange={handleFilterChange}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="정당 검색"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">선거구</label>
            <input
              type="text"
              name="constituency"
              value={filters.constituency}
              onChange={handleFilterChange}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="선거구 검색"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">대수</label>
            <input
              type="text"
              name="era_co"
              value={filters.era_co}
              onChange={handleFilterChange}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="예: 21"
            />
          </div>
        </div>
      </div>

      {/* Speakers List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {speakers.map(speaker => (
          <div key={speaker.id} className="bg-white rounded-lg shadow overflow-hidden">
            <div className="p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="h-12 w-12 rounded-full bg-gray-200 flex items-center justify-center">
                    <span className="text-xl font-bold text-gray-500">
                      {speaker.naas_nm.charAt(0)}
                    </span>
                  </div>
                </div>
                <div className="ml-4">
                  <Link
                    to={`/speakers/${speaker.id}`}
                    className="text-lg font-medium text-gray-900 hover:text-blue-600"
                  >
                    {speaker.naas_nm}
                  </Link>
                  <p className="text-sm text-gray-500">{speaker.plpt_nm}</p>
                </div>
              </div>
              <div className="mt-4">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">선거구:</span> {speaker.constituency}
                </p>
                <p className="text-sm text-gray-600">
                  <span className="font-medium">대수:</span> {speaker.era_co}대
                </p>
                <p className="text-sm text-gray-600">
                  <span className="font-medium">평균 감성 점수:</span>{' '}
                  <span className={`${
                    speaker.avg_sentiment > 0.3 ? 'text-green-600' :
                    speaker.avg_sentiment < -0.3 ? 'text-red-600' :
                    'text-gray-600'
                  }`}>
                    {speaker.avg_sentiment?.toFixed(2) || 'N/A'}
                  </span>
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="mt-8 flex justify-center">
        <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            이전
          </button>
          <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            다음
          </button>
        </nav>
      </div>
    </div>
  );
}

export default SpeakerList;