import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

const SentimentChart = ({ data }) => {
  // Transform data for the chart
  const processChartData = () => {
    // Handle multiple possible data structures
    let dataArray = [];
    
    if (Array.isArray(data)) {
      dataArray = data;
    } else if (data?.data && Array.isArray(data.data)) {
      dataArray = data.data;
    } else if (data?.results && Array.isArray(data.results)) {
      dataArray = data.results;
    } else if (data?.party_analysis && Array.isArray(data.party_analysis)) {
      dataArray = data.party_analysis;
    } else if (data?.sentiment_summary) {
      // Handle bill sentiment data structure
      return [{
        name: 'Overall',
        sentiment: data.sentiment_summary.average_sentiment || 0,
        party: 'All Parties'
      }];
    }

    if (dataArray.length === 0) return [];

    return dataArray.map((item, index) => ({
      name: item.party_name || item.speaker?.naas_nm || item.name || `Item ${index + 1}`,
      sentiment: parseFloat(item.combined_sentiment || item.avg_sentiment || item.sentiment_score || 0),
      party: item.party_name || item.speaker?.plpt_nm || 'Unknown Party'
    }));
  };

  const chartData = processChartData();

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium">{label}</p>
          <p className="text-sm text-gray-600">
            정당: {data.party || 'Unknown'}
          </p>
          <p className="text-sm text-gray-600">
            감성 점수: {payload[0].value.toFixed(2)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="h-96 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          margin={{
            top: 20,
            right: 30,
            left: 20,
            bottom: 5,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis domain={[-1, 1]} />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Bar
            dataKey="sentiment"
            name="감성 점수"
            fill="#4F46E5"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default SentimentChart;