import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const SentimentChart = ({ data, title = "감성 분석 결과" }) => {
  // Transform and validate data
  const chartData = React.useMemo(() => {
    if (!data) return [];

    let processedData = [];

    // Handle different data structures
    if (Array.isArray(data)) {
      processedData = data;
    } else if (data.party_sentiment && Array.isArray(data.party_sentiment)) {
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
        party: "All Parties"
      }];
    }

    if (processedData.length === 0) return [];

    return processedData.map((item, index) => ({
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
    }));
  }, [data]);

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

  const barData = chartData.map(item => ({
    name: item.name,
    value: item.sentiment,
    party: item.party,
    statement_count: item.statement_count,
    positive_count: item.positive_count,
    negative_count: item.negative_count
  }));

  const BarChart = () => {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={barData} margin={{ top: 15, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Bar dataKey="value" fill="#8884d8" />
        </BarChart>
      </ResponsiveContainer>
    );
  };

  return (
    <div className="space-y-4">
      <h2>{title}</h2>
      <BarChart />
    </div>
  );
};

export default SentimentChart;