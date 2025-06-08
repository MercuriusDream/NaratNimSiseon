import React from 'react';
import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const SentimentChart = ({ data, title = "감성 분석 결과" }) => {
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

  // For sentiment distribution, create data with three categories
  const sentimentBarData = React.useMemo(() => {
    if (chartData.length === 0) return [];

    // If we have overall sentiment data, create a single entry with three bars
    if (chartData.length === 1 && (chartData[0].name === "Overall" || chartData[0].name === "전체")) {
      const item = chartData[0];
      return [{
        name: "감성 분포",
        긍정: item.positive_count || 0,
        중립: item.neutral_count || (item.statement_count - (item.positive_count || 0) - (item.negative_count || 0)) || 0,
        부정: item.negative_count || 0
      }];
    }

    // For party-wise data, show each party with their sentiment breakdown
    return chartData.map(item => ({
      name: item.name,
      긍정: item.positive_count || 0,
      중립: item.neutral_count || 0,
      부정: item.negative_count || 0
    }));
  }, [chartData]);

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

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium">{label}</p>
          <p className="text-sm text-gray-600">정당: {data.party || "Unknown"}</p>
          <p className="text-sm text-gray-600">감성 점수: {payload[0].value.toFixed(2)}</p>
          {data.statement_count && (
            <p className="text-sm text-gray-600">총 발언: {data.statement_count}건</p>
          )}
          {data.positive_count !== undefined && (
            <p className="text-sm text-green-600">긍정: {data.positive_count}건</p>
          )}
          {data.negative_count !== undefined && (
            <p className="text-sm text-red-600">부정: {data.negative_count}건</p>
          )}
        </div>
      );
    }
    return null;
  };

  const CustomTooltipThreeBars = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const total = payload.reduce((sum, entry) => sum + entry.value, 0);
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium mb-2">{label}</p>
          <div className="space-y-1">
            {payload.map((entry, index) => (
              <p key={index} className="text-sm" style={{ color: entry.color }}>
                {entry.dataKey}: {entry.value}건 ({total > 0 ? ((entry.value / total) * 100).toFixed(1) : 0}%)
              </p>
            ))}
            <p className="text-sm font-medium border-t pt-1 mt-2">
              총 발언: {total}건
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
        <RechartsBarChart data={sentimentBarData} margin={{ top: 15, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip content={<CustomTooltipThreeBars />} />
          <Legend />
          <Bar dataKey="긍정" fill="#22c55e" name="긍정" />
          <Bar dataKey="중립" fill="#6b7280" name="중립" />
          <Bar dataKey="부정" fill="#ef4444" name="부정" />
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default SentimentChart;