import React from 'react';

const SentimentChart = ({ data }) => {
  if (!data) return null;

  // Handle different data structures
  let chartData = [];

  if (data && typeof data === 'object') {
    if (data.party_rankings && Array.isArray(data.party_rankings)) {
      // Overall sentiment stats data with party rankings
      chartData = data.party_rankings.slice(0, 10);
    } else if (data.party_analysis && Array.isArray(data.party_analysis)) {
      // Bill sentiment data
      chartData = data.party_analysis;
    } else if (Array.isArray(data)) {
      chartData = data;
    } else {
      // Handle overall_stats object by creating a summary chart
      const totalStatements = data.total_statements || 0;
      const positiveCount = data.positive_count || 0;
      const neutralCount = data.neutral_count || 0;
      const negativeCount = data.negative_count || 0;

      if (totalStatements > 0) {
        // Calculate proportions as percentages
        const positiveScore = positiveCount / totalStatements;
        const neutralScore = neutralCount / totalStatements;
        const negativeScore = negativeCount / totalStatements;

        chartData = [
          {
            speaker__plpt_nm: '긍정적 발언',
            party_name: '긍정적 발언',
            avg_sentiment: positiveScore,
            sentiment_score: positiveScore,
            statement_count: positiveCount,
            positive_count: positiveCount,
            negative_count: 0,
            proportion: (positiveScore * 100).toFixed(1) + '%',
            isDistribution: true,
            distributionType: 'positive'
          },
          {
            speaker__plpt_nm: '중립적 발언',
            party_name: '중립적 발언',
            statement_count: neutralCount,
            positive_count: 0,
            negative_count: 0,
            proportion: (neutralScore * 100).toFixed(1) + '%',
            avg_sentiment: neutralScore,
            isDistribution: true,
            distributionType: 'neutral'
          },
          {
            speaker__plpt_nm: '부정적 발언',
            party_name: '부정적 발언',
            avg_sentiment: -negativeScore,
            sentiment_score: -negativeScore,
            statement_count: negativeCount,
            positive_count: 0,
            negative_count: negativeCount,
            proportion: (negativeScore * 100).toFixed(1) + '%',
            isDistribution: true,
            distributionType: 'negative'
          }
        ].filter(item => item.statement_count > 0); // Only show categories with data
      } else {
        chartData = [];
      }
    }
  } else if (Array.isArray(data)) {
    chartData = data;
  } else {
    chartData = [];
  }

  if (!chartData || chartData.length === 0) {
    // Show a default empty state chart instead of just text
    return (
      <div className="space-y-4">
        <div className="text-center text-gray-600 py-8">
          <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p className="text-lg font-medium text-gray-900 mb-2">감성 분석 데이터 없음</p>
          <p className="text-sm text-gray-500">분석할 발언 데이터가 아직 없습니다.</p>
        </div>
      </div>
    );
  }

  // Function to calculate gradient color based on sentiment score
  const getSentimentColor = (sentimentScore) => {
    const normalizedScore = (sentimentScore + 1) / 2; // Normalize score to 0-1 range
    const red = Math.round(255 * (1 - normalizedScore));
    const green = Math.round(255 * normalizedScore);
    const blue = 0;
    return `rgb(${red}, ${green}, ${blue})`;
  };

  // Function to get fixed color for distribution categories
  const getDistributionColor = (distributionType) => {
    switch (distributionType) {
      case 'positive':
        return '#22C55E'; // Green
      case 'neutral':
        return '#6B7280'; // Grey
      case 'negative':
        return '#EF4444'; // Red
      default:
        return '#6B7280'; // Default grey
    }
  };

  return (
    <div className="space-y-4">
      {chartData.map((item, index) => {
        const sentimentScore = item.avg_sentiment || item.sentiment_score || item.combined_sentiment || 0;
        const displayName = item.speaker__plpt_nm?.split('/').pop() || 
                           item.party_name || 
                           item.speaker_name || 
                           item.speaker__naas_nm ||
                           `항목 ${index + 1}`;
        const positiveCount = data.positive_count || 0;
        const neutralCount = data.neutral_count || 0;
        const negativeCount = data.negative_count || 0;

        const isDistribution = item.isDistribution;
        const barColor = isDistribution 
          ? getDistributionColor(item.distributionType)
          : getSentimentColor(sentimentScore);
        const barWidth = isDistribution 
          ? `${Math.max(Math.min((item.statement_count / (positiveCount + neutralCount + negativeCount)) * 100, 100), 5)}%`
          : `${Math.max(Math.min(Math.abs(sentimentScore) * 100, 100), 5)}%`;

        return (
          <div key={index} className="border-b pb-4 last:border-b-0">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">
                {displayName}
              </span>
              <div 
                className="px-2 py-1 rounded text-xs text-white font-medium"
                style={{ backgroundColor: barColor }}
              >
                {isDistribution 
                  ? item.proportion
                  : sentimentScore.toFixed(3)
                }
              </div>
            </div>

            <div className="w-full bg-gray-200 rounded-full h-3 relative">
              <div
                className={`h-3 rounded-full transition-all duration-300`}
                style={{
                  width: barWidth,
                  backgroundColor: barColor
                }}
              ></div>
            </div>

            <div className="text-xs text-gray-600 mt-1 flex space-x-4">
              {item.statement_count && (
                <span>발언 수: {item.statement_count}건</span>
              )}
              {item.proportion && (
                <span>비율: {item.proportion}</span>
              )}
              {item.positive_count !== undefined && item.positive_count > 0 && (
                <span>긍정: {item.positive_count}건</span>
              )}
              {item.negative_count !== undefined && item.negative_count > 0 && (
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