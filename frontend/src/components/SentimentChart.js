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
    const dataArray = Array.isArray(data) ? data : 
                     (data?.data && Array.isArray(data.data)) ? data.data : 
                     (data?.results && Array.isArray(data.results)) ? data.results : [];

    if (dataArray.length === 0) return [];

    return dataArray.map(item => ({
      date: item.date || item.session?.conf_dt || 'Unknown',
      sentiment: parseFloat(item.sentiment_score || 0),
      speaker: item.speaker?.naas_nm || 'Unknown Speaker'
    }));
  };

  const chartData = processChartData();

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium">{label}</p>
          <p className="text-sm text-gray-600">
            정당: {payload[0].payload.party}
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