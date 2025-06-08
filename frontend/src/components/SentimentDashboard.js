import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import SentimentChart from './SentimentChart';

const SentimentDashboard = ({ billId = null }) => {
  const [sentimentData, setSentimentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('all');
  const [error, setError] = useState(null);

  const fetchSentimentData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      if (billId) {
        const response = await api.get(`/api/bills/${billId}/voting-sentiment/`);
        setSentimentData(response.data);
      } else {
        const response = await api.get(`/api/analytics/sentiment/overall/?time_range=${timeRange}`);
        setSentimentData(response.data);
      }
    } catch (err) {
      console.error('Error fetching sentiment data:', err);
      setError('감성 분석 데이터를 불러오는 중 오류가 발생했습니다.');
      setSentimentData(null);
    } finally {
      setLoading(false);
    }
  }, [billId, timeRange]);

  useEffect(() => {
    fetchSentimentData();
  }, [fetchSentimentData]);

  

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600 bg-green-50 border-green-200';
    if (score < -0.3) return 'text-red-600 bg-red-50 border-red-200';
    return 'text-gray-600 bg-gray-50 border-gray-200';
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-300 rounded w-1/4 mb-4"></div>
          <div className="space-y-3">
            <div className="h-4 bg-gray-300 rounded"></div>
            <div className="h-4 bg-gray-300 rounded w-5/6"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-red-600 text-center">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {!billId && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">전체 감성 분석</h2>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">전체 기간</option>
              <option value="1month">최근 1개월</option>
              <option value="3months">최근 3개월</option>
              <option value="6months">최근 6개월</option>
            </select>
          </div>

          {sentimentData && sentimentData.overall_stats && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {sentimentData.overall_stats.positive_count || 0}
                </div>
                <div className="text-sm text-gray-600">긍정적 발언</div>
                <div className="text-xs text-gray-500">
                  ({sentimentData.overall_stats.positive_percentage || 0}%)
                </div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-600">
                  {sentimentData.overall_stats.neutral_count || 0}
                </div>
                <div className="text-sm text-gray-600">중립적 발언</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">
                  {sentimentData.overall_stats.negative_count || 0}
                </div>
                <div className="text-sm text-gray-600">부정적 발언</div>
                <div className="text-xs text-gray-500">
                  ({sentimentData.overall_stats.negative_percentage || 0}%)
                </div>
              </div>
            </div>
          )}

          {sentimentData && sentimentData.overall_stats && (
            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="text-center">
                  <div className="text-lg font-semibold text-gray-900">
                    {sentimentData.overall_stats.total_statements || 0}
                  </div>
                  <div className="text-sm text-gray-600">총 발언 수</div>
                </div>
                <div className="text-center">
                  <div className={`text-lg font-semibold ${
                    (sentimentData.overall_stats.average_sentiment || 0) > 0 ? 'text-green-600' : 
                    (sentimentData.overall_stats.average_sentiment || 0) < 0 ? 'text-red-600' : 'text-gray-600'
                  }`}>
                    {(sentimentData.overall_stats.average_sentiment || 0).toFixed(3)}
                  </div>
                  <div className="text-sm text-gray-600">평균 감성 점수</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {sentimentData && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">
            {billId ? '의안별 감성 분석' : '감성 분석 차트'}
          </h3>
          <SentimentChart data={sentimentData} />
        </div>
      )}

      {sentimentData && Array.isArray(sentimentData.party_rankings) && sentimentData.party_rankings.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">정당별 감성 순위</h3>
          <div className="space-y-3">
            {sentimentData.party_rankings.slice(0, 10).map((party, index) => (
              <div key={index} className="flex items-center justify-between p-3 border border-gray-200 rounded-lg">
                <div className="flex-1">
                  <div className="font-medium text-gray-900 text-sm">
                    {party.speaker__plpt_nm?.split('/').pop() || party.speaker__plpt_nm}
                  </div>
                  <div className="text-xs text-gray-600">
                    발언 수: {party.statement_count} | 긍정: {party.positive_count} | 부정: {party.negative_count}
                  </div>
                </div>
                <div className={`px-3 py-1 rounded text-sm font-medium ${getSentimentColor(party.avg_sentiment)}`}>
                  {party.avg_sentiment?.toFixed(3)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {sentimentData && Array.isArray(sentimentData.active_speakers) && sentimentData.active_speakers.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">활동적인 발언자</h3>
          <div className="space-y-3">
            {sentimentData.active_speakers.slice(0, 10).map((speaker, index) => (
              <div key={index} className="flex items-center justify-between p-3 border border-gray-200 rounded-lg">
                <div className="flex-1">
                  <div className="font-medium text-gray-900 text-sm">
                    {speaker.speaker__naas_nm}
                  </div>
                  <div className="text-xs text-gray-600">
                    {speaker.speaker__plpt_nm?.split('/').pop() || speaker.speaker__plpt_nm} | 발언 수: {speaker.statement_count}
                  </div>
                </div>
                <div className={`px-3 py-1 rounded text-sm font-medium ${getSentimentColor(speaker.avg_sentiment)}`}>
                  {speaker.avg_sentiment?.toFixed(3)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {sentimentData && Array.isArray(sentimentData.recent_statements) && sentimentData.recent_statements.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">최근 주요 발언</h3>
          <div className="space-y-4">
            {sentimentData.recent_statements.map((statement, index) => (
              <div key={index} className="border-l-4 border-blue-200 pl-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-900">
                    {statement.speaker_name}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs ${getSentimentColor(statement.sentiment_score)}`}>
                    감성 점수: {statement.sentiment_score?.toFixed(2)}
                  </span>
                </div>
                <p className="text-gray-700 text-sm">
                  {statement.content?.substring(0, 200)}...
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {(!sentimentData || (
        !sentimentData.overall_stats && 
        !sentimentData.party_analysis && 
        !sentimentData.party_rankings && 
        (!sentimentData.party_rankings || sentimentData.party_rankings.length === 0)
      )) && !loading && !error && (
        <div className="bg-white rounded-lg shadow p-6 text-center text-gray-600">
          표시할 감성 데이터가 없습니다.
        </div>
      )}
    </div>
  );
};

export default SentimentDashboard;