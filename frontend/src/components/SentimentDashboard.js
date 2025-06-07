
import React, { useState, useEffect } from 'react';
import api from '../api';

const SentimentDashboard = ({ billId = null, partyId = null }) => {
  const [sentimentData, setSentimentData] = useState(null);
  const [overallStats, setOverallStats] = useState(null);
  const [categoryData, setCategoryData] = useState(null);
  const [partyData, setPartyData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('all');
  const [selectedParty, setSelectedParty] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSentimentData();
  }, [billId, partyId, timeRange, selectedParty, selectedCategory]);

  const fetchSentimentData = async () => {
    try {
      setLoading(true);
      setError(null);

      const promises = [];

      if (billId) {
        // Fetch bill-specific sentiment data
        promises.push(api.get(`/api/bills/${billId}/sentiment/`));
      } else if (partyId) {
        // Fetch party-specific sentiment data
        promises.push(api.get(`/api/parties/${partyId}/sentiment/?time_range=${timeRange}`));
      } else {
        // Fetch overall sentiment statistics
        promises.push(api.get(`/api/analytics/sentiment/?time_range=${timeRange}`));
        
        // Fetch category-based sentiment analysis
        const categoryParams = new URLSearchParams({
          time_range: timeRange,
          ...(selectedParty && { party: selectedParty }),
          ...(selectedCategory && { category: selectedCategory })
        });
        promises.push(api.get(`/api/analytics/category-sentiment/?${categoryParams}`));
      }

      const responses = await Promise.all(promises);

      if (billId) {
        setSentimentData(responses[0].data);
      } else if (partyId) {
        setPartyData(responses[0].data);
      } else {
        setOverallStats(responses[0].data);
        setCategoryData(responses[1].data);
      }
    } catch (error) {
      console.error('Error fetching sentiment data:', error);
      setError('감성 분석 데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600 bg-green-50 border-green-200';
    if (score < -0.3) return 'text-red-600 bg-red-50 border-red-200';
    return 'text-gray-600 bg-gray-50 border-gray-200';
  };

  const getSentimentLabel = (score) => {
    if (score > 0.3) return '긍정적';
    if (score < -0.3) return '부정적';
    return '중립적';
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-300 rounded w-1/4 mb-4"></div>
          <div className="space-y-3">
            <div className="h-4 bg-gray-300 rounded"></div>
            <div className="h-4 bg-gray-300 rounded w-5/6"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-red-600 text-center">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters for Overall Stats */}
      {!billId && !partyId && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <h2 className="text-2xl font-bold">종합 감성 분석</h2>
            <div className="flex flex-wrap gap-2">
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="border border-gray-300 rounded-md px-3 py-2"
              >
                <option value="all">전체 기간</option>
                <option value="year">최근 1년</option>
                <option value="month">최근 1달</option>
              </select>
              <input
                type="text"
                placeholder="정당명 필터"
                value={selectedParty}
                onChange={(e) => setSelectedParty(e.target.value)}
                className="border border-gray-300 rounded-md px-3 py-2"
              />
              <input
                type="text"
                placeholder="카테고리 필터"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="border border-gray-300 rounded-md px-3 py-2"
              />
            </div>
          </div>
        </div>
      )}

      {/* Party-specific Filter */}
      {partyId && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold">정당 감성 분석</h2>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-2"
            >
              <option value="all">전체 기간</option>
              <option value="year">최근 1년</option>
              <option value="month">최근 1달</option>
            </select>
          </div>
        </div>
      )}

      {/* Bill-specific Sentiment Analysis */}
      {billId && sentimentData && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-2xl font-bold mb-4">의안 감성 분석</h2>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-800">{sentimentData.bill.name}</h3>
          </div>
          
          {/* Sentiment Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
              <h4 className="font-semibold text-blue-800">총 발언 수</h4>
              <p className="text-2xl font-bold text-blue-600">
                {sentimentData.sentiment_summary.total_statements}
              </p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg border border-green-200">
              <h4 className="font-semibold text-green-800">긍정적 발언</h4>
              <p className="text-2xl font-bold text-green-600">
                {sentimentData.sentiment_summary.positive_count}
              </p>
              <p className="text-sm text-green-600">
                ({sentimentData.sentiment_summary.positive_percentage}%)
              </p>
            </div>
            <div className="bg-red-50 p-4 rounded-lg border border-red-200">
              <h4 className="font-semibold text-red-800">부정적 발언</h4>
              <p className="text-2xl font-bold text-red-600">
                {sentimentData.sentiment_summary.negative_count}
              </p>
              <p className="text-sm text-red-600">
                ({sentimentData.sentiment_summary.negative_percentage}%)
              </p>
            </div>
            <div className={`p-4 rounded-lg border ${getSentimentColor(sentimentData.sentiment_summary.average_sentiment)}`}>
              <h4 className="font-semibold">평균 감성 점수</h4>
              <p className="text-2xl font-bold">
                {sentimentData.sentiment_summary.average_sentiment}
              </p>
              <p className="text-sm">
                ({getSentimentLabel(sentimentData.sentiment_summary.average_sentiment)})
              </p>
            </div>
          </div>

          {/* Party Breakdown */}
          {sentimentData.party_breakdown.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">정당별 감성 분석</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">정당</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">발언 수</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">평균 감성</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">긍정/부정</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {sentimentData.party_breakdown.map((party, index) => (
                      <tr key={index}>
                        <td className="px-6 py-4 whitespace-nowrap font-medium">{party.speaker__plpt_nm}</td>
                        <td className="px-6 py-4 whitespace-nowrap">{party.count}</td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`px-2 py-1 rounded-full text-sm ${getSentimentColor(party.avg_sentiment)}`}>
                            {party.avg_sentiment.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <span className="text-green-600">{party.positive_count}</span> / 
                          <span className="text-red-600 ml-1">{party.negative_count}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Timeline */}
          {sentimentData.sentiment_timeline.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-3">감성 변화 추이</h3>
              <div className="space-y-2">
                {sentimentData.sentiment_timeline.map((item, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                    <span className="font-medium">{item.date}</span>
                    <div className="flex items-center space-x-3">
                      <span className="text-sm text-gray-600">{item.statement_count}개 발언</span>
                      <span className={`px-2 py-1 rounded text-sm ${getSentimentColor(item.avg_sentiment)}`}>
                        {item.avg_sentiment}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Category Analysis */}
      {!billId && !partyId && categoryData && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">카테고리별 감성 분석</h3>
          <div className="space-y-4">
            {categoryData.results.map((category, index) => (
              <div key={index} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-lg font-medium">{category.category_name}</h4>
                  <div className="flex items-center space-x-3">
                    <span className="text-sm text-gray-600">{category.statement_count}개 발언</span>
                    <span className={`px-3 py-1 rounded-full text-sm ${getSentimentColor(category.avg_sentiment)}`}>
                      {category.avg_sentiment}
                    </span>
                  </div>
                </div>
                
                {/* Sentiment Distribution */}
                <div className="grid grid-cols-3 gap-2 mb-3">
                  <div className="bg-green-50 p-2 rounded text-center">
                    <div className="text-sm text-green-700">긍정</div>
                    <div className="text-lg font-bold text-green-600">
                      {category.positive_count} ({category.positive_percentage}%)
                    </div>
                  </div>
                  <div className="bg-gray-50 p-2 rounded text-center">
                    <div className="text-sm text-gray-700">중립</div>
                    <div className="text-lg font-bold text-gray-600">
                      {category.neutral_count}
                    </div>
                  </div>
                  <div className="bg-red-50 p-2 rounded text-center">
                    <div className="text-sm text-red-700">부정</div>
                    <div className="text-lg font-bold text-red-600">
                      {category.negative_count} ({category.negative_percentage}%)
                    </div>
                  </div>
                </div>

                {/* Subcategory Breakdown */}
                {category.subcategory_breakdown.length > 0 && (
                  <div className="mb-3">
                    <h5 className="text-sm font-medium text-gray-700 mb-2">하위 카테고리</h5>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {category.subcategory_breakdown.map((subcat, subIndex) => (
                        <div key={subIndex} className="bg-gray-50 p-2 rounded text-xs">
                          <div className="font-medium">{subcat.subcategory_name}</div>
                          <div className="text-gray-600">
                            {subcat.statement_count}건 / {subcat.avg_sentiment}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Party Breakdown */}
                {category.party_breakdown.length > 0 && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">정당별 감성</h5>
                    <div className="space-y-1">
                      {category.party_breakdown.slice(0, 5).map((party, partyIndex) => (
                        <div key={partyIndex} className="flex items-center justify-between text-sm">
                          <span>{party.speaker__plpt_nm} ({party.count}건)</span>
                          <span className={`px-2 py-1 rounded text-xs ${getSentimentColor(party.avg_sentiment)}`}>
                            {party.avg_sentiment.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Party Analysis */}
      {partyData && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">
            {partyData.party.name} 감성 분석 ({partyData.time_range})
          </h3>
          
          {/* Party Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <h4 className="font-semibold text-blue-800">소속 의원</h4>
              <p className="text-2xl font-bold text-blue-600">
                {partyData.overall_stats.total_members}명
              </p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <h4 className="font-semibold text-green-800">총 발언</h4>
              <p className="text-2xl font-bold text-green-600">
                {partyData.overall_stats.total_statements}
              </p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="font-semibold text-purple-800">총 투표</h4>
              <p className="text-2xl font-bold text-purple-600">
                {partyData.overall_stats.total_votes}
              </p>
            </div>
            <div className={`p-4 rounded-lg ${getSentimentColor(partyData.overall_stats.avg_statement_sentiment)}`}>
              <h4 className="font-semibold">평균 감성</h4>
              <p className="text-2xl font-bold">
                {partyData.overall_stats.avg_statement_sentiment}
              </p>
            </div>
          </div>

          {/* Category Breakdown */}
          {partyData.category_breakdown.length > 0 && (
            <div className="mb-6">
              <h4 className="text-lg font-semibold mb-3">카테고리별 활동</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {partyData.category_breakdown.map((category, index) => (
                  <div key={index} className="bg-gray-50 p-3 rounded">
                    <div className="font-medium text-sm">{category.category_name}</div>
                    <div className="text-xs text-gray-600">{category.statement_count}건 발언</div>
                    <div className={`text-sm font-medium ${
                      category.avg_sentiment > 0.3 ? 'text-green-600' :
                      category.avg_sentiment < -0.3 ? 'text-red-600' : 'text-gray-600'
                    }`}>
                      감성: {category.avg_sentiment}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Member Analysis */}
          {partyData.member_analysis.length > 0 && (
            <div>
              <h4 className="text-lg font-semibold mb-3">의원별 감성 분석</h4>
              <div className="space-y-2">
                {partyData.member_analysis.slice(0, 10).map((member, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                    <div>
                      <span className="font-medium">{member.member_name}</span>
                      <div className="text-sm text-gray-600">
                        발언 {member.statement_count}건 / 투표 {member.voting_count}건
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-600">
                        발언: {member.avg_statement_sentiment} / 투표: {member.avg_voting_sentiment}
                      </div>
                      <span className={`px-3 py-1 rounded-full text-sm ${getSentimentColor(member.combined_sentiment)}`}>
                        종합: {member.combined_sentiment}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Overall Statistics */}
      {!billId && !partyId && overallStats && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">전체 통계 ({overallStats.time_range})</h3>
          
          {/* Overall Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <h4 className="font-semibold text-blue-800">총 발언 수</h4>
              <p className="text-2xl font-bold text-blue-600">
                {overallStats.overall_stats.total_statements}
              </p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <h4 className="font-semibold text-green-800">긍정적 발언</h4>
              <p className="text-2xl font-bold text-green-600">
                {overallStats.overall_stats.positive_count}
              </p>
              <p className="text-sm text-green-600">
                ({overallStats.overall_stats.positive_percentage}%)
              </p>
            </div>
            <div className="bg-red-50 p-4 rounded-lg">
              <h4 className="font-semibold text-red-800">부정적 발언</h4>
              <p className="text-2xl font-bold text-red-600">
                {overallStats.overall_stats.negative_count}
              </p>
              <p className="text-sm text-red-600">
                ({overallStats.overall_stats.negative_percentage}%)
              </p>
            </div>
            <div className={`p-4 rounded-lg ${getSentimentColor(overallStats.overall_stats.average_sentiment)}`}>
              <h4 className="font-semibold">평균 감성 점수</h4>
              <p className="text-2xl font-bold">
                {overallStats.overall_stats.average_sentiment}
              </p>
            </div>
          </div>

          {/* Party Rankings */}
          {overallStats.party_rankings.length > 0 && (
            <div className="mb-6">
              <h4 className="text-lg font-semibold mb-3">정당별 감성 순위</h4>
              <div className="space-y-2">
                {overallStats.party_rankings.slice(0, 5).map((party, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                    <div>
                      <span className="font-medium">{party.speaker__plpt_nm}</span>
                      <span className="text-sm text-gray-600 ml-2">({party.statement_count}개 발언)</span>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-sm ${getSentimentColor(party.avg_sentiment)}`}>
                      {party.avg_sentiment.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Active Speakers */}
          {overallStats.active_speakers.length > 0 && (
            <div>
              <h4 className="text-lg font-semibold mb-3">활발한 발언자</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {overallStats.active_speakers.slice(0, 10).map((speaker, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                    <div>
                      <span className="font-medium">{speaker.speaker__naas_nm}</span>
                      <span className="text-sm text-gray-600 block">{speaker.speaker__plpt_nm}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-600">{speaker.statement_count}개 발언</div>
                      <span className={`px-2 py-1 rounded text-xs ${getSentimentColor(speaker.avg_sentiment)}`}>
                        {speaker.avg_sentiment.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SentimentDashboard;
