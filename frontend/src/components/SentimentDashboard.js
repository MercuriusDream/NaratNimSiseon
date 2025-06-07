
import React, { useState, useEffect } from 'react';
import SentimentChart from './SentimentChart';
import api from '../api';

const SentimentDashboard = () => {
  const [sentimentData, setSentimentData] = useState(null);
  const [categoryData, setCategoryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('all');
  const [selectedParty, setSelectedParty] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');

  const fetchSentimentData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch comprehensive sentiment analysis
      const params = new URLSearchParams({
        time_range: timeRange,
        ...(selectedParty && { party: selectedParty }),
        ...(selectedCategory && { category: selectedCategory }),
      });

      const [comprehensiveResponse, categoryResponse] = await Promise.all([
        api.get(`/analytics/sentiment/comprehensive/?${params}`),
        api.get(`/analytics/sentiment/categories/?${params}`)
      ]);

      setSentimentData(comprehensiveResponse.data);
      setCategoryData(categoryResponse.data);
    } catch (err) {
      console.error('Error fetching sentiment data:', err);
      setError('감성 분석 데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSentimentData();
  }, [timeRange, selectedParty, selectedCategory]);

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600 bg-green-50 border-green-200';
    if (score < -0.3) return 'text-red-600 bg-red-50 border-red-200';
    return 'text-gray-600 bg-gray-50 border-gray-200';
  };

  const getSentimentLabel = (score) => {
    if (score > 0.3) return '긍정적';
    if (score < -0.3) return '부정적';
    return '중립적';
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-300 rounded w-1/4 mb-6"></div>
          <div className="space-y-4">
            <div className="h-20 bg-gray-300 rounded"></div>
            <div className="h-40 bg-gray-300 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-center text-red-600">
          <p>{error}</p>
          <button 
            onClick={fetchSentimentData}
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              기간
            </label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-2"
            >
              <option value="all">전체</option>
              <option value="year">최근 1년</option>
              <option value="month">최근 1개월</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              정당
            </label>
            <input
              type="text"
              value={selectedParty}
              onChange={(e) => setSelectedParty(e.target.value)}
              placeholder="정당명 입력"
              className="border border-gray-300 rounded-md px-3 py-2"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              카테고리
            </label>
            <input
              type="text"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              placeholder="카테고리명 입력"
              className="border border-gray-300 rounded-md px-3 py-2"
            />
          </div>
        </div>
      </div>

      {/* Overall Statistics */}
      {sentimentData && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Speech-based Sentiment */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">발언 기반 감성 분석</h3>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-gray-600">총 발언 수:</span>
                <span className="font-medium">{sentimentData.speech_sentiment.total_statements.toLocaleString()}개</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">평균 감성 점수:</span>
                <span className={`px-2 py-1 rounded text-sm font-medium ${getSentimentColor(sentimentData.speech_sentiment.avg_sentiment)}`}>
                  {sentimentData.speech_sentiment.avg_sentiment.toFixed(3)} ({getSentimentLabel(sentimentData.speech_sentiment.avg_sentiment)})
                </span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-green-600">긍정적 발언:</span>
                  <span className="font-medium">{sentimentData.speech_sentiment.positive_count}개</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-red-600">부정적 발언:</span>
                  <span className="font-medium">{sentimentData.speech_sentiment.negative_count}개</span>
                </div>
              </div>
            </div>
          </div>

          {/* Voting-based Sentiment */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">투표 기반 감성 분석</h3>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-gray-600">총 투표 수:</span>
                <span className="font-medium">{sentimentData.voting_sentiment.total_votes.toLocaleString()}개</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">평균 감성 점수:</span>
                <span className={`px-2 py-1 rounded text-sm font-medium ${getSentimentColor(sentimentData.voting_sentiment.avg_sentiment)}`}>
                  {sentimentData.voting_sentiment.avg_sentiment.toFixed(3)} ({getSentimentLabel(sentimentData.voting_sentiment.avg_sentiment)})
                </span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-green-600">찬성 투표:</span>
                  <span className="font-medium">{sentimentData.voting_sentiment.positive_votes}개</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-red-600">반대 투표:</span>
                  <span className="font-medium">{sentimentData.voting_sentiment.negative_votes}개</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">기권/불참:</span>
                  <span className="font-medium">{sentimentData.voting_sentiment.abstain_votes}개</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Party Analysis */}
      {sentimentData?.party_analysis && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">정당별 감성 분석</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    정당
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    발언 감성
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    투표 감성
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    종합 감성
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {sentimentData.party_analysis.slice(0, 10).map((party, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {party.party_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div className={`px-2 py-1 rounded text-sm ${getSentimentColor(party.speech_sentiment.avg_sentiment)}`}>
                        {party.speech_sentiment.avg_sentiment.toFixed(3)}
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {party.speech_sentiment.count}개 발언
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div className={`px-2 py-1 rounded text-sm ${getSentimentColor(party.voting_sentiment.avg_sentiment)}`}>
                        {party.voting_sentiment.avg_sentiment.toFixed(3)}
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {party.voting_sentiment.count}개 투표
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div className={`px-2 py-1 rounded text-sm font-medium ${getSentimentColor(party.combined_sentiment)}`}>
                        {party.combined_sentiment.toFixed(3)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Category Analysis */}
      {categoryData?.category_analysis && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">카테고리별 감성 분석</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {categoryData.category_analysis.map((category) => (
              <div key={category.category_id} className="border border-gray-200 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 mb-2">{category.category_name}</h4>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">발언 수:</span>
                    <span>{category.total_statements}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">평균 감성:</span>
                    <span className={`px-2 py-1 rounded text-xs ${getSentimentColor(category.avg_sentiment)}`}>
                      {category.avg_sentiment}
                    </span>
                  </div>
                </div>
                
                {/* Top parties in this category */}
                {category.party_breakdown?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <h5 className="text-xs font-medium text-gray-700 mb-2">상위 정당</h5>
                    <div className="space-y-1">
                      {category.party_breakdown.slice(0, 3).map((party, idx) => (
                        <div key={idx} className="flex justify-between text-xs">
                          <span className="text-gray-600 truncate">{party.speaker__plpt_nm || '정당정보없음'}</span>
                          <span className={`px-1 rounded ${getSentimentColor(party.avg_sentiment)}`}>
                            {party.avg_sentiment?.toFixed(2) || 'N/A'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chart Visualization */}
      {sentimentData?.party_analysis && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">정당별 감성 점수 차트</h3>
          <SentimentChart data={sentimentData.party_analysis.map(party => ({
            name: party.party_name,
            sentiment: party.combined_sentiment,
            party: party.party_name,
            speech_count: party.speech_sentiment.count,
            voting_count: party.voting_sentiment.count
          }))} />
        </div>
      )}
    </div>
  );
};

export default SentimentDashboard;
