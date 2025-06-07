import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';
import { Link } from 'react-router-dom';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import SentimentChart from '../components/SentimentChart';

function PartyDetail() {
  const { id } = useParams();
  const [party, setParty] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('all'); // 'all', 'month', 'year'
  const [sortBy, setSortBy] = useState('sentiment'); // 'sentiment', 'statements', 'bills'

  useEffect(() => {
    fetchPartyData();
  }, [id, timeRange, sortBy, fetchPartyData]);

  const fetchPartyData = async (fetchAdditional = false) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        time_range: timeRange,
        sort_by: sortBy
      });
      if (fetchAdditional) {
        params.append('fetch_additional', 'true');
      }
      
      const response = await api.get(
        `/api/parties/${id}/?${params.toString()}`
      );
      setParty(response.data);
      
      if (response.data.additional_data_fetched) {
        console.log('Additional data fetch triggered for party');
      }
    } catch (err) {
      setError('데이터를 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching party data:', err);
    } finally {
      setLoading(false);
    }
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

  if (!party) {
    return (
      <div className="text-center text-gray-600 p-4">
        정당 정보를 찾을 수 없습니다.
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <div className="container mx-auto px-4 py-8">
      {/* Party Header */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-3xl font-bold">{party.name}</h1>
          <button
            onClick={() => fetchPartyData(true)}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? '데이터 새로고침 중...' : '최신 데이터 가져오기'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">의원 수:</span>{' '}
              {party.member_count}명
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">평균 감성 점수:</span>{' '}
              <span className={`${
                party.avg_sentiment > 0.3 ? 'text-green-600' :
                party.avg_sentiment < -0.3 ? 'text-red-600' :
                'text-gray-600'
              }`}>
                {party.avg_sentiment?.toFixed(2) || 'N/A'}
              </span>
            </p>
          </div>
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">총 발언 수:</span>{' '}
              {party.total_statements || 0}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">총 의안 수:</span>{' '}
              {(party.approved_bills || 0) + (party.rejected_bills || 0)}
            </p>
          </div>
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">가결 의안:</span>{' '}
              {party.approved_bills || 0}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">부결 의안:</span>{' '}
              {party.rejected_bills || 0}
            </p>
          </div>
        </div>
      </div>

      {/* Time Range Filter */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
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

      {/* Sentiment Analysis */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">감성 분석 결과</h2>
        <SentimentChart data={party.recent_statements || []} />
      </div>

      {/* Members List */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold">의원 목록</h2>
          <div className="flex space-x-2">
            <button
              onClick={() => setSortBy('sentiment')}
              className={`px-3 py-1 rounded-md text-sm ${
                sortBy === 'sentiment'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              감성 점수순
            </button>
            <button
              onClick={() => setSortBy('statements')}
              className={`px-3 py-1 rounded-md text-sm ${
                sortBy === 'statements'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              발언 수순
            </button>
            <button
              onClick={() => setSortBy('bills')}
              className={`px-3 py-1 rounded-md text-sm ${
                sortBy === 'bills'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              의안 수순
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  이름
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  선거구
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  감성 점수
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  발언 수
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  의안 수
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {party.members?.map(member => (
                <tr key={member.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      to={`/speakers/${member.id}`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-900"
                    >
                      {member.naas_nm}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {member.constituency}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      member.avg_sentiment > 0.3 ? 'bg-green-100 text-green-800' :
                      member.avg_sentiment < -0.3 ? 'bg-red-100 text-red-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {member.avg_sentiment?.toFixed(2) || 'N/A'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {member.total_statements || 0}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {(member.approved_bills || 0) + (member.rejected_bills || 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default PartyDetail;