import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { Link } from 'react-router-dom';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import SentimentChart from '../components/SentimentChart';
import CategoryChart from '../components/CategoryChart';
import CategoryFilter from '../components/CategoryFilter';

function PartyList() {
  const [parties, setParties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('all');
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [categoryData, setCategoryData] = useState([]);
  const [showCategoryFilter, setShowCategoryFilter] = useState(false);

  const fetchPartiesCallback = useCallback(async (fetchAdditional = false) => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({ time_range: timeRange });
      if (selectedCategories.length > 0) {
        params.append('categories', selectedCategories.join(','));
      }
      if (fetchAdditional) {
        params.append('fetch_additional', 'true');
      }

      const response = await api.get(`/api/parties/?${params.toString()}`);

      // Handle different response structures and ensure we always have an array
      let partiesData = [];
      if (response.data) {
        if (Array.isArray(response.data)) {
          partiesData = response.data;
        } else if (response.data.results && Array.isArray(response.data.results)) {
          partiesData = response.data.results;
        } else if (response.data.data && Array.isArray(response.data.data)) {
          partiesData = response.data.data;
        } else {
          // If no recognizable array structure, default to empty array
          console.warn('Unexpected parties data structure:', response.data);
          partiesData = [];
        }
      }

      // Double-check that partiesData is always an array
      if (!Array.isArray(partiesData)) {
        console.warn('Parties data is not an array after processing:', partiesData);
        partiesData = [];
      }

      setParties(partiesData);

      if (response.data && response.data.additional_data_fetched) {
        console.log('Additional data fetch triggered');
      }
    } catch (err) {
      const errorMessage = err.response?.status === 500 
        ? '서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
        : '데이터를 불러오는 중 오류가 발생했습니다.';
      setError(errorMessage);
      console.error('Error fetching parties:', err);
      setParties([]); // Ensure parties is set to empty array on error
    } finally {
      setLoading(false);
    }
  }, [timeRange, selectedCategories]);

  useEffect(() => {
    const loadParties = async () => {
      try {
        setLoading(true);
        const { fetchParties } = await import('../api');
        const response = await fetchParties();
        setParties(Array.isArray(response) ? response : response.results || []);
      } catch (err) {
        console.error('Error fetching parties:', err);
        setError('정당 데이터를 불러오는 중 오류가 발생했습니다.');
      } finally {
        setLoading(false);
      }
    };

    loadParties();
  }, [timeRange]);

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

  if (!Array.isArray(parties) || parties.length === 0) {
    return (
      <div className="flex overflow-hidden flex-col bg-white min-h-screen">
        <NavigationHeader />
        <main className="flex flex-col w-full">
          <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8">정당 목록</h1>
            <div className="text-center text-gray-600 p-4">
              표시할 정당이 없습니다.
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <div className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">정당 목록</h1>
          <button
            onClick={() => fetchPartiesCallback(true)}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? '데이터 새로고침 중...' : '최신 데이터 가져오기'}
          </button>
        </div>

      {/* Filters */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        <div className="lg:col-span-3">
          {/* Time Range Filter */}
          <div className="bg-white rounded-lg shadow p-6 mb-4">
            <h3 className="text-lg font-semibold mb-4">기간 필터</h3>
            <div className="flex justify-center space-x-4">
              <button
                onClick={() => setTimeRange('all')}
                className={`px-4 py-2 rounded-md ${
                  timeRange === 'all'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                전체
              </button>
              <button
                onClick={() => setTimeRange('year')}
                className={`px-4 py-2 rounded-md ${
                  timeRange === 'year'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                최근 1년
              </button>
              <button
                onClick={() => setTimeRange('month')}
                className={`px-4 py-2 rounded-md ${
                  timeRange === 'month'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                최근 1개월
              </button>
            </div>
          </div>

          {/* Category Analytics */}
          {categoryData.length > 0 && (
            <CategoryChart data={categoryData} title="카테고리별 정당 감성 분석" />
          )}
        </div>

        {/* Category Filter Sidebar */}
        <div className="lg:col-span-1">
          <CategoryFilter 
            onCategoryChange={setSelectedCategories}
            selectedCategories={selectedCategories}
          />
        </div>
      </div>

      {/* Parties Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Array.isArray(parties) && parties.map(party => (
          <div key={party.id} className="bg-white rounded-lg shadow overflow-hidden">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center mr-3">
                    <span className="text-blue-600 font-bold">
                      {party.name ? party.name.charAt(0) : '정'}
                    </span>
                  </div>
                  <Link
                    to={`/parties/${party.id}`}
                    className="text-xl font-bold text-gray-900 hover:text-blue-600"
                  >
                    {party.name}
                  </Link>
                </div>
                <span className="text-sm text-gray-500">
                  {party.member_count || 0}명
                </span>
              </div>

              {/* Party Stats */}
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">평균 감성 점수:</span>{' '}
                    <span className={`${
                      (party.avg_sentiment || 0) > 0.3 ? 'text-green-600' :
                      (party.avg_sentiment || 0) < -0.3 ? 'text-red-600' :
                      'text-gray-600'
                    }`}>
                      {party.avg_sentiment?.toFixed(2) || 'N/A'}
                    </span>
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">총 발언 수:</span>{' '}
                    {party.total_statements || 0}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">가결 의안:</span>{' '}
                    {party.approved_bills || 0}
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">부결 의안:</span>{' '}
                    {party.rejected_bills || 0}
                  </p>
                </div>
              </div>

              {/* Sentiment Chart */}
              {party.recent_statements && Array.isArray(party.recent_statements) && party.recent_statements.length > 0 && (
                <div className="h-48 mb-4">
                  <SentimentChart data={party.recent_statements} />
                </div>
              )}

              {/* Top Members */}
              {party.top_members && Array.isArray(party.top_members) && party.top_members.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">주요 의원</h3>
                  <div className="space-y-2">
                    {party.top_members.map((member, index) => (
                      <div key={member.id || member.naas_nm || index} className="flex items-center justify-between text-sm">
                        <Link
                          to={`/speakers/${member.id || member.naas_cd}`}
                          className="text-gray-600 hover:text-blue-600"
                        >
                          {member.naas_nm || 'Unknown'}
                        </Link>
                        <span className={`${
                          (member.avg_sentiment || 0) > 0.3 ? 'text-green-600' :
                          (member.avg_sentiment || 0) < -0.3 ? 'text-red-600' :
                          'text-gray-600'
                        }`}>
                          {member.avg_sentiment?.toFixed(2) || 'N/A'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default PartyList;