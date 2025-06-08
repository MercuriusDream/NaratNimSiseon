import React, { useState, useEffect } from 'react';
import api from '../api';

const StatementList = ({ filters = {} }) => {
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({});
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    fetchStatements();
  }, [filters, currentPage]);

  const fetchStatements = async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      params.append('page', currentPage);
      if (sessionId) {
        params.append('session', sessionId);
      }
      if (billId) {
        params.append('bill', billId);
      }

      const response = await api.get(`/api/statements/?${params}`).catch(() => ({
        data: { results: [], count: 0, next: null, previous: null }
      }));

      // Handle different response structures
      const statementsData = response.data?.results || response.data || [];
      const paginationData = {
        count: response.data?.count || statementsData.length,
        next: response.data?.next,
        previous: response.data?.previous
      };

      setStatements(Array.isArray(statementsData) ? statementsData : []);
      setPagination(paginationData);
    } catch (err) {
      setError('발언 목록을 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching statements:', err);
      setStatements([]);
      setPagination({ count: 0, next: null, previous: null });
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600 bg-green-100';
    if (score < -0.3) return 'text-red-600 bg-red-100';
    return 'text-gray-600 bg-gray-100';
  };

  const getSentimentLabel = (score) => {
    if (score > 0.3) return 'Positive';
    if (score < -0.3) return 'Negative';
    return 'Neutral';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">발언 목록</h2>
        <div className="text-sm text-gray-500">
          총 {pagination.count}개의 발언
        </div>
      </div>

      <div className="space-y-4">
        {Array.isArray(statements) && statements.map((statement) => (
          <div key={statement.id} className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {statement.speaker_name}
                </h3>
                <p className="text-sm text-gray-600">
                  {statement.party_name} | {statement.session_date}
                </p>
                {statement.bill_name && (
                  <p className="text-sm text-blue-600 mt-1">
                    관련 의안: {statement.bill_name}
                  </p>
                )}
              </div>
              <div className={`px-3 py-1 rounded-full text-xs font-medium ${getSentimentColor(statement.sentiment_score)}`}>
                {getSentimentLabel(statement.sentiment_score)} ({statement.sentiment_score?.toFixed(2)})
              </div>
            </div>

            <p className="text-gray-700 leading-relaxed mb-4">
              {statement.text.length > 300 
                ? `${statement.text.substring(0, 300)}...` 
                : statement.text}
            </p>

            {statement.policy_keywords && (
              <div className="flex flex-wrap gap-2">
                {statement.policy_keywords.split(',').slice(0, 5).map((keyword, index) => (
                  <span key={index} className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                    {keyword.trim()}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex justify-center space-x-2 mt-8">
        <button
          onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
          disabled={!pagination.previous}
          className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          이전
        </button>
        <span className="px-4 py-2 text-gray-700">
          페이지 {currentPage}
        </span>
        <button
          onClick={() => setCurrentPage(prev => prev + 1)}
          disabled={!pagination.next}
          className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          다음
        </button>
      </div>
    </div>
  );
};

export default StatementList;