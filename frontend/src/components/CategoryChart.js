
import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const CategoryChart = ({ data, title = "카테고리별 감성 분석" }) => {
  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg">
        <p className="text-gray-500">표시할 카테고리 데이터가 없습니다.</p>
      </div>
    );
  }

  // Transform data for the chart
  const chartData = data.map(item => ({
    category: item.category_name || item.name,
    positive: item.positive_count || 0,
    neutral: item.neutral_count || 0,
    negative: item.negative_count || 0,
    avg_sentiment: item.avg_sentiment || 0
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-4 border border-gray-200 shadow-lg rounded">
          <p className="font-medium mb-2">{label}</p>
          <div className="space-y-1">
            <p className="text-sm text-green-600">
              긍정: {data.positive}건
            </p>
            <p className="text-sm text-gray-600">
              중립: {data.neutral}건
            </p>
            <p className="text-sm text-red-600">
              부정: {data.negative}건
            </p>
            <p className="text-sm font-medium">
              평균 감성: {data.avg_sentiment.toFixed(2)}
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div className="h-96 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            margin={{
              top: 20,
              right: 30,
              left: 20,
              bottom: 60,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis 
              dataKey="category" 
              angle={-45}
              textAnchor="end"
              height={80}
              interval={0}
            />
            <YAxis />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Bar dataKey="positive" name="긍정" fill="#10B981" />
            <Bar dataKey="neutral" name="중립" fill="#6B7280" />
            <Bar dataKey="negative" name="부정" fill="#EF4444" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default CategoryChart;
