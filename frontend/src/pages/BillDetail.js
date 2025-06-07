import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';

const BillDetail = () => {
  const { billId } = useParams();
  const [bill, setBill] = useState(null);
  const [statements, setStatements] = useState([]);
  const [sentimentData, setSentimentData] = useState(null);
  const [votingRecords, setVotingRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fetchingVoting, setFetchingVoting] = useState(false);

  const fetchVotingRecords = async () => {
    try {
      setFetchingVoting(true);
      await api.post('/analytics/voting/fetch/', {
        bill_id: billId,
        force: false
      });
      // Refresh bill data to get updated voting records
      const billResponse = await api.get(`/bills/${billId}/`);
      setBill(billResponse.data);
      setVotingRecords(billResponse.data.voting_records || []);
    } catch (err) {
      console.error('Error fetching voting records:', err);
    } finally {
      setFetchingVoting(false);
    }
  };

  useEffect(() => {
    const fetchBillDetails = async () => {
      try {
        setLoading(true);
        const [billResponse, statementsResponse, sentimentResponse] = await Promise.all([
          api.get(`/bills/${billId}/`),
          api.get(`/bills/${billId}/statements/`),
          api.get(`/analytics/bills/${billId}/sentiment/`)
        ]);

        setBill(billResponse.data);
        setStatements(statementsResponse.data.data || []);
        setSentimentData(sentimentResponse.data);
        setVotingRecords(billResponse.data.voting_records || []);
      } catch (err) {
        console.error('Error fetching bill details:', err);
        setError('의안 상세 정보를 불러오는 중 오류가 발생했습니다.');
      } finally {
        setLoading(false);
      }
    };

    if (billId) {
      fetchBillDetails();
    }
  }, [billId]);

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600 bg-green-50 border-green-200';
    if (score < -0.3) return 'text-red-600 bg-red-50 border-red-200';
    return 'text-gray-600 bg-gray-50 border-gray-200';
  };

  const getVoteColor = (vote) => {
    if (vote === '찬성') return 'text-green-600 bg-green-50';
    if (vote === '반대') return 'text-red-600 bg-red-50';
    return 'text-gray-600 bg-gray-50';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-300 rounded w-3/4 mb-4"></div>
            <div className="h-4 bg-gray-300 rounded w-1/2 mb-8"></div>
            <div className="space-y-4">
              <div className="h-40 bg-gray-300 rounded"></div>
              <div className="h-60 bg-gray-300 rounded"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-4">{bill?.bill_name}</h1>

        {/* Bill Details */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">의안 정보</h2>
          <p>의안 ID: {bill?.bill_id}</p>
          <p>제안자: {bill?.proposer}</p>
          <p>상태: {bill?.status}</p>
          {/* Add more bill details here */}
        </div>

        {/* Sentiment Analysis */}
        {sentimentData && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">감성 분석</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="text-center">
                <div className={`mx-auto w-20 h-20 rounded-full flex items-center justify-center mb-2 ${getSentimentColor(sentimentData.sentiment_summary?.average_sentiment || 0)}`}>
                  <span className="text-2xl font-bold">
                    {(sentimentData.sentiment_summary?.average_sentiment || 0).toFixed(2)}
                  </span>
                </div>
                <p className="text-sm text-gray-600">평균 감성 점수</p>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-green-600 mb-2">
                  {sentimentData.sentiment_summary?.positive_count || 0}
                </div>
                <p className="text-sm text-gray-600">긍정적 발언</p>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-red-600 mb-2">
                  {sentimentData.sentiment_summary?.negative_count || 0}
                </div>
                <p className="text-sm text-gray-600">부정적 발언</p>
              </div>
            </div>

            {/* Party Breakdown */}
            {sentimentData.party_breakdown && sentimentData.party_breakdown.length > 0 && (
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-3">정당별 감성</h3>
                <div className="space-y-2">
                  {sentimentData.party_breakdown.slice(0, 5).map((party, index) => (
                    <div key={index} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                      <span className="font-medium">{party.speaker__plpt_nm || '정당정보없음'}</span>
                      <div className="text-right">
                        <span className={`px-2 py-1 rounded text-sm ${getSentimentColor(party.avg_sentiment)}`}>
                          {party.avg_sentiment?.toFixed(2) || 'N/A'}
                        </span>
                        <span className="text-xs text-gray-500 ml-2">
                          ({party.count}개 발언)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Voting Records */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-gray-900">투표 기록</h2>
            <button
              onClick={fetchVotingRecords}
              disabled={fetchingVoting}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
            >
              {fetchingVoting ? '가져오는 중...' : '투표 기록 가져오기'}
            </button>
          </div>

          {votingRecords.length > 0 ? (
            <div>
              {/* Voting Summary */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div className="text-center">
                  <div className="text-2xl font-bold text-gray-900 mb-1">
                    {votingRecords.length}
                  </div>
                  <p className="text-sm text-gray-600">총 투표 수</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600 mb-1">
                    {votingRecords.filter(v => v.vote_result === '찬성').length}
                  </div>
                  <p className="text-sm text-gray-600">찬성</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-red-600 mb-1">
                    {votingRecords.filter(v => v.vote_result === '반대').length}
                  </div>
                  <p className="text-sm text-gray-600">반대</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-gray-600 mb-1">
                    {votingRecords.filter(v => ['기권', '불참', '무효'].includes(v.vote_result)).length}
                  </div>
                  <p className="text-sm text-gray-600">기권/불참</p>
                </div>
              </div>

              {/* Voting Records Table */}
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        의원명
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        정당
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        투표 결과
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        투표 일시
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {votingRecords.slice(0, 20).map((record, index) => (
                      <tr key={index}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                          {record.speaker_name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {record.party_name || '정당정보없음'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          <span className={`px-2 py-1 rounded text-sm ${getVoteColor(record.vote_result)}`}>
                            {record.vote_result}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {new Date(record.vote_date).toLocaleString('ko-KR')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {votingRecords.length > 20 && (
                <p className="text-sm text-gray-500 mt-4 text-center">
                  {votingRecords.length - 20}개의 추가 투표 기록이 있습니다.
                </p>
              )}
            </div>
          ) : (
            <div className="text-center text-gray-500 py-8">
              이 의안에 대한 투표 기록이 없습니다.
              <br />
              <span className="text-sm">위 버튼을 클릭하여 투표 기록을 가져와 보세요.</span>
            </div>
          )}
        </div>

        {/* Statements */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">관련 발언</h2>
          {statements.length > 0 ? (
            <ul>
              {statements.map(statement => (
                <li key={statement.id} className="py-2 border-b last:border-b-0">
                  <p className="text-gray-800">{statement.content}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    발언자: {statement.speaker?.name || '알 수 없음'}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500">관련 발언이 없습니다.</p>
          )}
        </div>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
            <strong className="font-bold">Error!</strong>
            <span className="block sm:inline">{error}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default BillDetail;