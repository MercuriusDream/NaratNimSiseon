import React from 'react';

const SentimentChart = ({ data }) => {
  if (!data) return null;

  // Handle different data structures
  let chartData = [];

  if (data.party_rankings && Array.isArray(data.party_rankings)) {
    // Overall sentiment stats data with party rankings
    chartData = data.party_rankings.slice(0, 10);
  } else if (data.party_analysis && Array.isArray(data.party_analysis)) {
    // Bill sentiment data
    chartData = data.party_analysis;
  } else if (Array.isArray(data)) {
    chartData = data;
  } else if (data && typeof data === 'object') {
    // Handle overall_stats object by creating a summary chart
    if (data.total_statements && data.total_statements > 0) {
      chartData = [
        {
          speaker__plpt_nm: '긍정적 발언',
          party_name: '긍정적 발언',
          avg_sentiment: 0.5,
          sentiment_score: 0.5,
          statement_count: data.positive_count || 0,
          positive_count: data.positive_count || 0,
          negative_count: 0
        },
        {
          speaker__plpt_nm: '중립적 발언',
          party_name: '중립적 발언', 
          avg_sentiment: 0,
          sentiment_score: 0,
          statement_count: data.neutral_count || 0,
          positive_count: 0,
          negative_count: 0
        },
        {
          speaker__plpt_nm: '부정적 발언',
          party_name: '부정적 발언',
          avg_sentiment: -0.5,
          sentiment_score: -0.5,
          statement_count: data.negative_count || 0,
          positive_count: 0,
          negative_count: data.negative_count || 0
        }
      ].filter(item => item.statement_count > 0); // Only show categories with data
    } else {
      chartData = [];
    }
  } else {
    chartData = [];
  }

  if (!chartData || chartData.length === 0) {
    return (
      <div className="text-center text-gray-600 py-4">
        표시할 차트 데이터가 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {chartData.map((item, index) => {
        const sentimentScore = item.avg_sentiment || item.sentiment_score || item.combined_sentiment || 0;
        const displayName = item.speaker__plpt_nm?.split('/').pop() || 
                           item.party_name || 
                           item.speaker_name || 
                           item.speaker__naas_nm ||
                           `항목 ${index + 1}`;

        return (
          <div key={index} className="border-b pb-4 last:border-b-0">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">
                {displayName}
              </span>
              <span className={`px-2 py-1 rounded text-xs ${
                sentimentScore > 0.3
                  ? 'bg-green-100 text-green-800'
                  : sentimentScore < -0.3
                  ? 'bg-red-100 text-red-800'
                  : 'bg-gray-100 text-gray-800'
              }`}>
                {sentimentScore.toFixed(3)}
              </span>
            </div>

            <div className="w-full bg-gray-200 rounded-full h-3 relative">
              <div
                className={`h-3 rounded-full transition-all duration-300 ${
                  sentimentScore > 0.3
                    ? 'bg-green-500'
                    : sentimentScore < -0.3
                    ? 'bg-red-500'
                    : 'bg-gray-400'
                }`}
                style={{
                  width: `${Math.max(Math.min(Math.abs(sentimentScore) * 100, 100), 5)}%`
                }}
              ></div>
            </div>

            <div className="text-xs text-gray-600 mt-1 flex space-x-4">
              {item.statement_count && (
                <span>발언 수: {item.statement_count}건</span>
              )}
              {item.positive_count !== undefined && (
                <span>긍정: {item.positive_count}건</span>
              )}
              {item.negative_count !== undefined && (
                <span>부정: {item.negative_count}건</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SentimentChart;