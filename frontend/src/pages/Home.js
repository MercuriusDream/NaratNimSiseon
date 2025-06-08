import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import Layout from '../components/Layout';
import SentimentChart from '../components/SentimentChart';

const Home = () => {
  const [homeData, setHomeData] = useState(null);
  const [sentimentData, setSentimentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchHomeData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch data with fallbacks for missing endpoints
        const dataPromises = [
          api.get('/api/sessions/').catch(() => ({ data: { results: [] } })),
          api.get('/api/bills/').catch(() => ({ data: { results: [] } })),
          api.get('/api/statements/').catch(() => ({ data: { results: [] } })),
          api.get('/api/analytics/overall/').catch(() => ({ data: { total_statements: 0, average_sentiment: 0, positive_count: 0, neutral_count: 0, negative_count: 0 } })),
          api.get('/api/analytics/parties/').catch(() => ({ data: { results: [] } }))
        ];

        const [sessionsRes, billsRes, statementsRes, overallStatsRes, partyStatsRes] = await Promise.all(dataPromises);

        // Extract and limit recent data
        const recentSessions = (Array.isArray(sessionsRes.data) ? sessionsRes.data : sessionsRes.data?.results || []).slice(0, 5);
        const recentBills = (Array.isArray(billsRes.data) ? billsRes.data : billsRes.data?.results || []).slice(0, 5);
        const recentStatements = (Array.isArray(statementsRes.data) ? statementsRes.data : statementsRes.data?.results || []).slice(0, 10);
        const partyStats = Array.isArray(partyStatsRes.data) ? partyStatsRes.data : partyStatsRes.data?.results || [];

        console.log('Home data response:', {
          recent_sessions: recentSessions,
          recent_bills: recentBills,
          recent_statements: recentStatements,
          overall_stats: overallStatsRes.data,
          party_stats: partyStats
        });

        setHomeData({
          recent_sessions: recentSessions,
          recent_bills: recentBills,
          recent_statements: recentStatements,
          overall_stats: overallStatsRes.data || {
            total_statements: 0,
            average_sentiment: 0,
            positive_count: 0,
            neutral_count: 0,
            negative_count: 0
          },
          party_stats: partyStats,
          total_sessions: (Array.isArray(sessionsRes.data) ? sessionsRes.data : sessionsRes.data?.results || []).length,
          total_bills: (Array.isArray(billsRes.data) ? billsRes.data : billsRes.data?.results || []).length,
          total_speakers: 300 // Default fallback
        });
      } catch (err) {
        console.error('Error fetching home data:', err);
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        // Set safe fallback data
        setHomeData({
          recent_sessions: [],
          recent_bills: [],
          recent_statements: [],
          overall_stats: {
            total_statements: 0,
            average_sentiment: 0,
            positive_count: 0,
            neutral_count: 0
          },
          party_stats: [],
          total_sessions: 0,
          total_bills: 0,
          total_speakers: 0
        });
      } finally {
        setLoading(false);
      }
    };

    fetchHomeData();
  }, []);

  if (loading) {
    return (
      <Layout>
        <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
          <div className="container mx-auto px-4 py-8">
            <div className="animate-pulse">
              <div className="h-8 bg-gray-300 rounded w-1/3 mb-6"></div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                {[1, 2, 3].map(i => (
                  <div key={i} className="bg-white rounded-lg shadow p-6">
                    <div className="h-4 bg-gray-300 rounded w-3/4 mb-3"></div>
                    <div className="h-6 bg-gray-300 rounded w-1/2"></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-md">
            <div className="text-red-600 text-center">
              <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.728-.833-2.498 0L4.316 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <p className="text-lg font-medium">{error}</p>
              <button 
                onClick={fetchHomeData}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                다시 시도
              </button>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
          <div className="container mx-auto px-4 py-16">
            <div className="text-center">
              <h1 className="text-4xl md:text-6xl font-bold mb-6">
                국회 의정활동 분석 시스템
              </h1>
              <p className="text-xl md:text-2xl text-blue-100 mb-8 max-w-3xl mx-auto">
                대한민국 국회의 의정활동을 투명하게 분석하고 시각화합니다
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link 
                  to="/sessions" 
                  className="px-8 py-4 bg-white text-blue-600 rounded-lg font-semibold hover:bg-blue-50 transition-colors shadow-lg"
                >
                  회의록 보기
                </Link>
                <Link 
                  to="/bills" 
                  className="px-8 py-4 bg-blue-500 text-white rounded-lg font-semibold hover:bg-blue-400 transition-colors shadow-lg"
                >
                  의안 분석
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="container mx-auto px-4 py-12">
          {/* Statistics Overview */}
          {homeData && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-12">
              <div className="bg-white rounded-xl shadow-lg p-6 text-center transform hover:scale-105 transition-transform">
                <div className="text-3xl font-bold text-blue-600 mb-2">
                  {homeData.total_sessions?.toLocaleString() || 0}
                </div>
                <div className="text-gray-600 font-medium">총 회의 수</div>
              </div>
              <div className="bg-white rounded-xl shadow-lg p-6 text-center transform hover:scale-105 transition-transform">
                <div className="text-3xl font-bold text-green-600 mb-2">
                  {homeData.total_bills?.toLocaleString() || 0}
                </div>
                <div className="text-gray-600 font-medium">총 의안 수</div>
              </div>
              <div className="bg-white rounded-xl shadow-lg p-6 text-center transform hover:scale-105 transition-transform">
                <div className="text-3xl font-bold text-purple-600 mb-2">
                  {homeData.total_speakers?.toLocaleString() || 0}
                </div>
                <div className="text-gray-600 font-medium">참여 의원 수</div>
              </div>
              <div className="bg-white rounded-xl shadow-lg p-6 text-center transform hover:scale-105 transition-transform">
                <div className="text-3xl font-bold text-orange-600 mb-2">
                  {homeData.overall_stats?.total_statements?.toLocaleString() || 0}
                </div>
                <div className="text-gray-600 font-medium">총 발언 수</div>
              </div>
            </div>
          )}

          {/* Sentiment Analysis Section */}
          {sentimentData && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
              <div className="bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
                  <svg className="h-6 w-6 text-blue-600 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  감성 분포
                </h2>
                <SentimentChart data={sentimentData} />
              </div>

              <div className="bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
                  <svg className="h-6 w-6 text-green-600 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                  주요 통계
                </h2>
                {homeData?.overall_stats && (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center p-4 bg-gray-50 rounded-lg">
                      <span className="font-medium text-gray-700">평균 감성 점수</span>
                      <span className={`font-bold text-lg ${
                        homeData.overall_stats.average_sentiment > 0 ? 'text-green-600' : 
                        homeData.overall_stats.average_sentiment < 0 ? 'text-red-600' : 'text-gray-600'
                      }`}>
                        {homeData.overall_stats.average_sentiment?.toFixed(3) || '0.000'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center p-4 bg-green-50 rounded-lg">
                      <span className="font-medium text-gray-700">긍정적 발언</span>
                      <span className="font-bold text-lg text-green-600">
                        {homeData.overall_stats.positive_count?.toLocaleString() || 0}건
                      </span>
                    </div>
                    <div className="flex justify-between items-center p-4 bg-gray-50 rounded-lg">
                      <span className="font-medium text-gray-700">중립적 발언</span>
                      <span className="font-bold text-lg text-gray-600">
                        {homeData.overall_stats.neutral_count?.toLocaleString() || 0}건
                      </span>
                    </div>
                    <div className="flex justify-between items-center p-4 bg-red-50 rounded-lg">
                      <span className="font-medium text-gray-700">부정적 발언</span>
                      <span className="font-bold text-lg text-red-600">
                        {homeData.overall_stats.negative_count?.toLocaleString() || 0}건
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Recent Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Recent Sessions */}
            <div className="bg-white rounded-xl shadow-lg p-8">
              <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
                <svg className="h-6 w-6 text-indigo-600 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                최근 회의록
              </h2>
              <div className="space-y-4">
                {homeData?.recent_sessions?.slice(0, 5).map((session) => (
                  <Link 
                    key={session.id} 
                    to={`/sessions/${session.id}`}
                    className="block p-4 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors"
                  >
                    <h3 className="font-semibold text-gray-800 mb-2 line-clamp-2">
                      {session.title}
                    </h3>
                    <div className="flex justify-between text-sm text-gray-600">
                      <span>{session.date}</span>
                      <span>{session.statement_count}건 발언</span>
                    </div>
                  </Link>
                )) || (
                  <div className="text-center text-gray-500 py-8">
                    <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p>최근 회의록이 없습니다</p>
                  </div>
                )}
              </div>
              <div className="mt-6 text-center">
                <Link 
                  to="/sessions" 
                  className="inline-flex items-center px-4 py-2 text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-600 hover:text-white transition-colors"
                >
                  모든 회의록 보기
                  <svg className="ml-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            </div>

            {/* Recent Bills */}
            <div className="bg-white rounded-xl shadow-lg p-8">
              <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
                <svg className="h-6 w-6 text-purple-600 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                최근 의안
              </h2>
              <div className="space-y-4">
                {homeData?.recent_bills?.slice(0, 5).map((bill) => (
                  <Link 
                    key={bill.id} 
                    to={`/bills/${bill.id}`}
                    className="block p-4 border border-gray-200 rounded-lg hover:bg-purple-50 hover:border-purple-300 transition-colors"
                  >
                    <h3 className="font-semibold text-gray-800 mb-2 line-clamp-2">
                      {bill.title}
                    </h3>
                    <div className="text-sm text-gray-600 mb-1">
                      발의자: {bill.proposer}
                    </div>
                    <div className="flex justify-between text-sm text-gray-500">
                      <span>{bill.session_title}</span>
                      <span>{bill.statement_count}건 발언</span>
                    </div>
                  </Link>
                )) || (
                  <div className="text-center text-gray-500 py-8">
                    <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p>최근 의안이 없습니다</p>
                  </div>
                )}
              </div>
              <div className="mt-6 text-center">
                <Link 
                  to="/bills" 
                  className="inline-flex items-center px-4 py-2 text-purple-600 border border-purple-600 rounded-lg hover:bg-purple-600 hover:text-white transition-colors"
                >
                  모든 의안 보기
                  <svg className="ml-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="mt-12 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl shadow-lg p-8 text-white">
            <h2 className="text-2xl font-bold mb-6 text-center">빠른 탐색</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <Link 
                to="/parties" 
                className="bg-white bg-opacity-20 rounded-lg p-6 text-center hover:bg-opacity-30 transition-all transform hover:scale-105"
              >
                <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
                <h3 className="font-semibold text-lg mb-2">정당별 분석</h3>
                <p className="text-sm opacity-90">각 정당의 의정활동을 분석합니다</p>
              </Link>
              <Link 
                to="/speakers" 
                className="bg-white bg-opacity-20 rounded-lg p-6 text-center hover:bg-opacity-30 transition-all transform hover:scale-105"
              >
                <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                <h3 className="font-semibold text-lg mb-2">의원별 활동</h3>
                <p className="text-sm opacity-90">개별 의원의 발언을 분석합니다</p>
              </Link>
              <Link 
                to="/sentiment" 
                className="bg-white bg-opacity-20 rounded-lg p-6 text-center hover:bg-opacity-30 transition-all transform hover:scale-105"
              >
                <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <h3 className="font-semibold text-lg mb-2">감성 분석</h3>
                <p className="text-sm opacity-90">발언의 감성을 분석합니다</p>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default Home;