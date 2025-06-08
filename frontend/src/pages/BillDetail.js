import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import SentimentChart from '../components/SentimentChart';

function BillDetail() {
  const { id } = useParams();
  const [bill, setBill] = useState(null);
  const [statements, setStatements] = useState([]);
  const [votingSentiment, setVotingSentiment] = useState(null);
  const [sentimentAnalysis, setSentimentAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBillData = async () => {
      try {
        setLoading(true);

        // Handle potential missing data gracefully
        const [billResponse, statementsResponse] = await Promise.all([
          axios.get(`/api/bills/${id}/`),
          axios.get(`/api/bills/${id}/statements/`)
        ]);

        // Ensure bill data is properly set
        setBill(billResponse.data);

        const statementsData = statementsResponse.data;

        // Handle different response structures and ensure we always have an array
        let statementsArray = [];
        if (statementsData?.status === 'success' && Array.isArray(statementsData.data)) {
          statementsArray = statementsData.data;
        } else if (Array.isArray(statementsData)) {
          statementsArray = statementsData;
        } else if (statementsData?.results && Array.isArray(statementsData.results)) {
          statementsArray = statementsData.results;
        }

        setStatements(statementsArray);

        // Try to fetch additional data, but don't fail if it's not available
        try {
          const [votingSentimentRes, sentimentRes] = await Promise.all([
            axios.get(`/api/bills/${id}/voting-sentiment/`),
            axios.get(`/api/bills/${id}/sentiment/`)
          ]);
          setVotingSentiment(votingSentimentRes.data);
          setSentimentAnalysis(sentimentRes.data);
        } catch (additionalError) {
          console.warn('Additional data not available:', additionalError);
          // Set default values to prevent crashes
          setVotingSentiment({
            summary: { total_statements: 0, total_voting_records: 0, vote_distribution: [] },
            party_analysis: []
          });
          setSentimentAnalysis({
            sentiment_summary: {
              total_statements: statementsArray.length,
              average_sentiment: 0,
              positive_count: 0,
              negative_count: 0,
              neutral_count: statementsArray.length
            },
            party_breakdown: [],
            speaker_breakdown: [],
            sentiment_timeline: []
          });
        }

      } catch (err) {
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        console.error('Error fetching bill data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchBillData();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center text-red-600 p-4">
        {error}
      </div>
    );
  }

  if (!bill) {
    return (
      <div className="text-center text-gray-600 p-4">
        의안 정보를 찾을 수 없습니다.
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <div className="container mx-auto px-4 py-8">
      {/* Bill Header */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h1 className="text-3xl font-bold mb-4">{bill.bill_nm || bill.bill_name}</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">의안번호:</span>{' '}
              {bill.bill_id || bill.bill_no || 'N/A'}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">제안자:</span>{' '}
              {bill.proposer || '국회'}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">회의:</span>{' '}
              {bill.session ? `${bill.session.era_co} ${bill.session.sess} ${bill.session.dgr}` : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">회의일:</span>{' '}
              {bill.session_date ? new Date(bill.session_date).toLocaleDateString('ko-KR') : 
               bill.created_at ? new Date(bill.created_at).toLocaleDateString('ko-KR') : 'N/A'}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">상태:</span>{' '}
              <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                bill.status === 'approved' ? 'bg-green-100 text-green-800' :
                bill.status === 'rejected' ? 'bg-red-100 text-red-800' :
                'bg-yellow-100 text-yellow-800'
              }`}>
                {bill.status === 'approved' ? '가결' :
                 bill.status === 'rejected' ? '부결' :
                 '심의중'}
              </span>
            </p>
            {bill.link_url && (
              <p className="text-gray-600">
                <a href={bill.link_url} target="_blank" rel="noopener noreferrer" 
                   className="text-blue-600 hover:text-blue-800 underline">
                  의안 상세 보기
                </a>
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Bill Content */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">의안 내용</h2>
        <div className="prose max-w-none">
          <p className="whitespace-pre-wrap">{bill.content || bill.bill_nm || '의안 내용을 불러올 수 없습니다.'}</p>
        </div>
      </div>

      {/* Voting and Sentiment Analysis */}
      {votingSentiment && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-2xl font-bold mb-4">투표 및 감성 분석</h2>

          {/* Summary Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <h3 className="font-semibold text-blue-800">총 발언 수</h3>
              <p className="text-2xl font-bold text-blue-600">{votingSentiment.summary?.total_statements || 0}</p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <h3 className="font-semibold text-green-800">총 투표 수</h3>
              <p className="text-2xl font-bold text-green-600">{votingSentiment.summary?.total_voting_records || 0}</p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <h3 className="font-semibold text-purple-800">참여 정당</h3>
              <p className="text-2xl font-bold text-purple-600">{votingSentiment.party_analysis?.length || 0}</p>
            </div>
          </div>

          {/* Vote Distribution */}
          {votingSentiment.summary?.vote_distribution && votingSentiment.summary.vote_distribution.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">투표 결과 분포</h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {votingSentiment.summary.vote_distribution.map((vote, index) => (
                  <div key={index} className={`p-3 rounded text-center ${
                    vote.vote_result === '찬성' ? 'bg-green-100 text-green-800' :
                    vote.vote_result === '반대' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    <div className="font-semibold">{vote.vote_result}</div>
                    <div className="text-lg font-bold">{vote.count}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Party Analysis */}
          {votingSentiment.party_analysis && votingSentiment.party_analysis.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">정당별 종합 감성 분석</h3>
              <div className="space-y-4">
                {votingSentiment.party_analysis.map((party, index) => (
                  <div key={index} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-lg font-medium">{party.party_name}</h4>
                      <div className="flex items-center space-x-4">
                        <span className="text-sm text-gray-600">발언: {party.statement_count}</span>
                        <span className="text-sm text-gray-600">투표: {party.voting_count}</span>
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                          party.combined_sentiment > 0.3 ? 'bg-green-100 text-green-800' :
                          party.combined_sentiment < -0.3 ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          종합: {party.combined_sentiment}
                        </span>
                      </div>
                    </div>

                    {/* Individual Members */}
                    {party.members && (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {Object.values(party.members).map((member, memberIndex) => (
                          <div key={memberIndex} className="bg-gray-50 p-3 rounded">
                            <div className="font-medium text-sm">{member.speaker_name}</div>
                            <div className="text-xs text-gray-600">
                              {member.vote_result && (
                                <span className={`inline-block px-2 py-1 rounded mr-2 ${
                                  member.vote_result === '찬성' ? 'bg-green-200 text-green-800' :
                                  member.vote_result === '반대' ? 'bg-red-200 text-red-800' :
                                  'bg-gray-200 text-gray-800'
                                }`}>
                                  {member.vote_result}
                                </span>
                              )}
                              {member.statements && member.statements.length > 0 && (
                                <span>발언 {member.statements.length}건</span>
                              )}
                            </div>
                            <div className="text-xs">
                              종합 감성: 
                              <span className={`ml-1 font-medium ${
                                member.combined_sentiment > 0.3 ? 'text-green-600' :
                                member.combined_sentiment < -0.3 ? 'text-red-600' :
                                'text-gray-600'
                              }`}>
                                {member.combined_sentiment}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Traditional Sentiment Analysis */}
      {sentimentAnalysis && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-2xl font-bold mb-4">발언 감성 분석</h2>
          <SentimentChart data={statements} />
        </div>
      )}

      {/* Related Statements */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-4">관련 발언</h2>
        <div className="space-y-6">
          {Array.isArray(statements) && statements.length > 0 ? (
            statements.map(statement => (
              <div key={statement.id} className="border-b pb-6 last:border-b-0">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h3 className="text-lg font-semibold">
                      {statement.speaker_name || statement.speaker?.naas_nm || '알 수 없는 발언자'}
                    </h3>
                    <p className="text-sm text-gray-600">
                      {statement.party_name || statement.speaker?.plpt_nm || ''}
                    </p>
                  </div>
                  <div className="text-sm">
                    <span className={`px-2 py-1 rounded ${
                      (statement.sentiment_score || 0) > 0.3 ? 'bg-green-100 text-green-800' :
                      (statement.sentiment_score || 0) < -0.3 ? 'bg-red-100 text-red-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      감성 점수: {statement.sentiment_score?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
                <p className="text-gray-700 whitespace-pre-wrap">
                  {statement.content || statement.text || '발언 내용을 불러올 수 없습니다.'}
                </p>
              </div>
            ))
          ) : (
            <div className="text-center text-gray-500 py-8">
              관련 발언이 없습니다.
            </div>
          )}
        </div>
      </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default BillDetail;