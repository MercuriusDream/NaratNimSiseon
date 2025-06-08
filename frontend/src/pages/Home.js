
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import Layout from '../components/Layout';
import SentimentChart from '../components/SentimentChart';

const Home = () => {
  const [homeData, setHomeData] = useState({
    recent_sessions: [],
    recent_bills: [],
    recent_statements: [],
    overall_stats: {},
    party_stats: [],
    total_sessions: 0,
    total_bills: 0,
    total_speakers: 0
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchHomeData();
  }, []);

  const fetchHomeData = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/home/');
      console.log('Home data response:', response.data);
      setHomeData(response.data);
      setError(null);
    } catch (error) {
      console.error('Error fetching home data:', error);
      setError('데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (score) => {
    if (score > 0.3) return 'text-green-600';
    if (score < -0.3) return 'text-red-600';
    return 'text-gray-600';
  };

  const getSentimentLabel = (score) => {
    if (score > 0.3) return '긍정적';
    if (score < -0.3) return '부정적';
    return '중립적';
  };

  const formatScore = (score) => {
    return (score || 0).toFixed(2);
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center min-h-screen">
          <div className="text-lg">데이터를 불러오는 중...</div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="flex justify-center items-center min-h-screen">
          <div className="text-red-600">{error}</div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-8">
        {/* Hero Section */}
        <div className="bg-blue-600 text-white py-16">
          <div className="max-w-7xl mx-auto px-4 text-center">
            <h1 className="text-4xl font-bold mb-4">국회 발언 분석 시스템</h1>
            <p className="text-xl">AI 기반 국회 발언 감성 분석 및 정책 동향 분석</p>
          </div>
        </div>

        {/* Statistics Overview */}
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600">총 회의</h3>
              <p className="text-3xl font-bold text-blue-600">{homeData.total_sessions}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600">총 의안</h3>
              <p className="text-3xl font-bold text-green-600">{homeData.total_bills}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600">총 발언</h3>
              <p className="text-3xl font-bold text-purple-600">{homeData.overall_stats.total_statements || 0}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600">평균 감성</h3>
              <p className={`text-3xl font-bold ${getSentimentColor(homeData.overall_stats.average_sentiment)}`}>
                {formatScore(homeData.overall_stats.average_sentiment)}
              </p>
            </div>
          </div>

          {/* Sentiment Analysis Chart */}
          {homeData.overall_stats.total_statements > 0 && (
            <div className="bg-white p-6 rounded-lg shadow mb-8">
              <h2 className="text-2xl font-bold mb-4">전체 감성 분석</h2>
              <SentimentChart data={homeData.overall_stats} />
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Recent Statements with LLM Analysis */}
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-bold mb-4">최근 발언 분석</h2>
              {homeData.recent_statements && homeData.recent_statements.length > 0 ? (
                <div className="space-y-4">
                  {homeData.recent_statements.map((statement) => (
                    <div key={statement.id} className="border-l-4 border-blue-500 pl-4 py-3 bg-gray-50 rounded">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <h4 className="font-semibold text-blue-600">{statement.speaker_name}</h4>
                          <p className="text-sm text-gray-600">{statement.speaker_party}</p>
                        </div>
                        <div className="text-right">
                          <span className={`font-semibold ${getSentimentColor(statement.sentiment_score)}`}>
                            {getSentimentLabel(statement.sentiment_score)} ({formatScore(statement.sentiment_score)})
                          </span>
                          {statement.bill_relevance_score > 0 && (
                            <p className="text-xs text-gray-500">
                              의안 관련도: {formatScore(statement.bill_relevance_score)}
                            </p>
                          )}
                        </div>
                      </div>
                      <p className="text-gray-700 text-sm mb-2">{statement.text}</p>
                      {statement.bill_title && (
                        <p className="text-xs text-blue-600">관련 의안: {statement.bill_title}</p>
                      )}
                      {statement.sentiment_reason && (
                        <p className="text-xs text-gray-500 mt-1">분석: {statement.sentiment_reason}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">아직 분석된 발언이 없습니다.</p>
              )}
            </div>

            {/* Party Statistics */}
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-bold mb-4">정당별 감성 통계</h2>
              {homeData.party_stats && homeData.party_stats.length > 0 ? (
                <div className="space-y-3">
                  {homeData.party_stats.map((party, index) => (
                    <div key={index} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                      <div>
                        <h4 className="font-semibold">{party.party_name}</h4>
                        <p className="text-sm text-gray-600">
                          의원 {party.member_count}명 · 발언 {party.statement_count}건
                        </p>
                      </div>
                      <div className="text-right">
                        <span className={`font-semibold ${getSentimentColor(party.avg_sentiment)}`}>
                          {formatScore(party.avg_sentiment)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">정당 통계를 불러올 수 없습니다.</p>
              )}
            </div>

            {/* Recent Sessions */}
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-bold mb-4">최근 회의</h2>
              {homeData.recent_sessions && homeData.recent_sessions.length > 0 ? (
                <div className="space-y-3">
                  {homeData.recent_sessions.map((session) => (
                    <Link
                      key={session.id}
                      to={`/sessions/${session.id}`}
                      className="block p-3 bg-gray-50 rounded hover:bg-gray-100 transition-colors"
                    >
                      <h4 className="font-semibold text-blue-600">{session.title}</h4>
                      <p className="text-sm text-gray-600">{session.committee}</p>
                      <p className="text-xs text-gray-500">
                        발언 {session.statement_count}건 · 의안 {session.bill_count}건
                      </p>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">최근 회의가 없습니다.</p>
              )}
            </div>

            {/* Recent Bills */}
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-bold mb-4">최근 의안</h2>
              {homeData.recent_bills && homeData.recent_bills.length > 0 ? (
                <div className="space-y-3">
                  {homeData.recent_bills.map((bill) => (
                    <Link
                      key={bill.id}
                      to={`/bills/${bill.id}`}
                      className="block p-3 bg-gray-50 rounded hover:bg-gray-100 transition-colors"
                    >
                      <h4 className="font-semibold text-blue-600">{bill.title}</h4>
                      <p className="text-sm text-gray-600">제안자: {bill.proposer}</p>
                      <p className="text-xs text-gray-500">발언 {bill.statement_count}건</p>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">최근 의안이 없습니다.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default Home;
