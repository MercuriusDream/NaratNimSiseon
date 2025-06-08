import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const SentimentChart = ({ data, title = "감성 분포" }) => {
  // Transform and validate data
  const chartData = React.useMemo(() => {
    if (!data) return [];

    let processedData = [];

    try {
      // Handle different data structures with better validation
      if (Array.isArray(data)) {
        processedData = data;
      } else if (data && typeof data === 'object') {
        if (data.party_sentiment && Array.isArray(data.party_sentiment)) {
          processedData = data.party_sentiment;
        } else if (data.results && Array.isArray(data.results)) {
          processedData = data.results;
        } else if (data.party_analysis && Array.isArray(data.party_analysis)) {
          processedData = data.party_analysis;
        } else if (data.sentiment_summary) {
          // Handle single sentiment summary
          return [{
            name: "Overall",
            sentiment: data.sentiment_summary.average_sentiment || 0,
            party: "All Parties",
            statement_count: data.sentiment_summary.total_statements || 0,
            positive_count: data.sentiment_summary.positive_count || 0,
            negative_count: data.sentiment_summary.negative_count || 0
          }];
        } else if (data.total_statements !== undefined) {
          // Handle overall stats format from home page
          return [{
            name: "Overall",
            sentiment: data.average_sentiment || 0,
            party: "전체",
            statement_count: data.total_statements || 0,
            positive_count: data.positive_count || 0,
            negative_count: data.negative_count || 0
          }];
        }
      }

      if (!Array.isArray(processedData) || processedData.length === 0) return [];

      return processedData.map((item, index) => {
        if (!item || typeof item !== 'object') return null;

        return {
          name: item.party_name || 
                item.speaker?.naas_nm || 
                item.name || 
                `Item ${index + 1}`,
          sentiment: parseFloat(item.combined_sentiment || item.avg_sentiment || item.sentiment_score || 0),
          party: item.party_name || 
                 item.speaker?.plpt_nm || 
                 "Unknown Party",
          statement_count: item.statement_count || 0,
          positive_count: item.positive_count || 0,
          negative_count: item.negative_count || 0
        };
      }).filter(Boolean); // Remove null entries
    } catch (error) {
      console.error('Error processing chart data:', error, data);
      return [];
    }
  }, [data]);

  // Create sentiment distribution histogram data
  const sentimentDistributionData = React.useMemo(() => {
    if (chartData.length === 0) return [];

    // Create sentiment bins from -1.0 to 1.0 with 0.05 intervals
    const bins = [];
    const binSize = 0.05;
    const minSentiment = -1.0;
    const maxSentiment = 1.0;
    const binCount = (maxSentiment - minSentiment) / binSize; // 40 bins total

    for (let i = 0; i < binCount; i++) {
      const binStart = minSentiment + (i * binSize);
      const binEnd = binStart + binSize;
      const binCenter = binStart + (binSize / 2);
      
      bins.push({
        sentimentRange: binCenter.toFixed(2),
        rangeLabel: `${binStart.toFixed(2)} to ${binEnd.toFixed(2)}`,
        count: 0,
        binStart,
        binEnd
      });
    }

    // Count statements in each bin
    chartData.forEach(item => {
      const sentiment = item.sentiment;
      const statementCount = item.statement_count || 1;
      
      // Find which bin this sentiment falls into
      for (let bin of bins) {
        if (sentiment >= bin.binStart && sentiment < bin.binEnd) {
          bin.count += statementCount;
          break;
        }
        // Handle edge case for exactly 1.0
        if (sentiment === 1.0 && bin.binEnd === 1.0) {
          bin.count += statementCount;
          break;
        }
      }
    });

    return bins;
  }, [chartData]);

  // Helper function to get color based on sentiment value
  const getSentimentColor = (sentiment) => {
    // Normalize sentiment from [-1, 1] to [0, 1]
    const normalized = Math.max(0, Math.min(1, (parseFloat(sentiment) + 1) / 2));
    
    if (normalized < 0.5) {
      // Red to Grey (negative to neutral)
      const ratio = normalized * 2; // 0 to 1
      const red = Math.round(239 + (107 - 239) * ratio); // 239 to 107
      const green = Math.round(68 + (114 - 68) * ratio);  // 68 to 114
      const blue = Math.round(68 + (128 - 68) * ratio);   // 68 to 128
      return `rgb(${red}, ${green}, ${blue})`;
    } else {
      // Grey to Green (neutral to positive)
      const ratio = (normalized - 0.5) * 2; // 0 to 1
      const red = Math.round(107 + (34 - 107) * ratio);   // 107 to 34
      const green = Math.round(114 + (197 - 114) * ratio); // 114 to 197
      const blue = Math.round(128 + (94 - 128) * ratio);   // 128 to 94
      return `rgb(${red}, ${green}, ${blue})`;
    }
  };

  if (!chartData || chartData.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
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

  const CustomTooltipHistogram = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const sentiment = parseFloat(label);
      const sentimentText = sentiment > 0.1 ? '긍정적' : sentiment < -0.1 ? '부정적' : '중립적';
      
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium mb-2">감성 범위: {data.rangeLabel}</p>
          <div className="space-y-1">
            <p className="text-sm" style={{ color: getSentimentColor(sentiment) }}>
              중심 점수: {sentiment.toFixed(2)} ({sentimentText})
            </p>
            <p className="text-sm font-medium">
              발언 수: {data.count}건
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={sentimentDistributionData} margin={{ top: 15, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="sentimentRange" 
            label={{ value: '감성 점수', position: 'insideBottom', offset: -5 }}
          />
          <YAxis 
            label={{ value: '발언 수', angle: -90, position: 'insideLeft' }}
          />
          <Tooltip content={<CustomTooltipHistogram />} />
          <Bar 
            dataKey="count" 
            name="발언 수"
            fill={(entry) => {
              // This won't work directly, but we'll handle it below
              return "#6b7280";
            }}
          >
            {sentimentDistributionData.map((entry, index) => (
              <Bar 
                key={`bar-${index}`}
                fill={getSentimentColor(parseFloat(entry.sentimentRange))}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default SentimentChart;