import React from 'react';

const SentimentChart = ({ data }) => {
  if (!data) return null;

  // Handle different data structures
  let chartData = [];

  if (data.party_rankings && Array.isArray(data.party_rankings)) {
    // Overall sentiment stats data
    chartData = data.party_rankings.slice(0, 10);
  } else if (data.party_analysis && Array.isArray(data.party_analysis)) {
    // Bill sentiment data
    chartData = data.party_analysis;
  } else if (Array.isArray(data)) {
    chartData = data;
  } else if (data && typeof data === 'object') {
    chartData = [data];
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

            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${
                  sentimentScore > 0.3
                    ? 'bg-green-500'
                    : sentimentScore < -0.3
                    ? 'bg-red-500'
                    : 'bg-gray-400'
                }`}
                style={{
                  width: `${Math.min(Math.abs(sentimentScore) * 100, 100)}%`
                }}
              ></div>
            </div>

            <div className="text-xs text-gray-600 mt-1 flex space-x-4">
              {item.statement_count && (
                <span>발언 수: {item.statement_count}</span>
              )}
              {item.positive_count !== undefined && (
                <span>긍정: {item.positive_count}</span>
              )}
              {item.negative_count !== undefined && (
                <span>부정: {item.negative_count}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SentimentChart;