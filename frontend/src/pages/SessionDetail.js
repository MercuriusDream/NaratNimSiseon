import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import SentimentChart from '../components/SentimentChart';

function SessionDetail() {
  const { id } = useParams();
  const [session, setSession] = useState(null);
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSessionData = async () => {
      try {
        setLoading(true);
        const [sessionRes, statementsRes] = await Promise.all([
          axios.get(`http://localhost:8000/api/sessions/${id}/`),
          axios.get(`http://localhost:8000/api/sessions/${id}/statements/`)
        ]);
        
        setSession(sessionRes.data);
        setStatements(statementsRes.data);
      } catch (err) {
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        console.error('Error fetching session data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSessionData();
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

  if (!session) {
    return (
      <div className="text-center text-gray-600 p-4">
        회의 정보를 찾을 수 없습니다.
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Session Header */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h1 className="text-3xl font-bold mb-4">
          {session.era_co}대 {session.sess}회 {session.dgr}차
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">날짜:</span>{' '}
              {new Date(session.conf_dt).toLocaleDateString('ko-KR')}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">시간:</span>{' '}
              {session.conf_time}
            </p>
          </div>
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">회의종류:</span>{' '}
              {session.conf_type}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">회의상태:</span>{' '}
              {session.conf_status}
            </p>
          </div>
        </div>
      </div>

      {/* Sentiment Analysis */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">감성 분석 결과</h2>
        <SentimentChart data={statements} />
      </div>

      {/* Statements List */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-4">발언 목록</h2>
        <div className="space-y-6">
          {statements.map(statement => (
            <div key={statement.id} className="border-b pb-6 last:border-b-0">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h3 className="text-lg font-semibold">
                    {statement.speaker.naas_nm}
                  </h3>
                  <p className="text-sm text-gray-600">
                    {statement.speaker.plpt_nm}
                  </p>
                </div>
                <div className="text-sm">
                  <span className={`px-2 py-1 rounded ${
                    statement.sentiment_score > 0.3 ? 'bg-green-100 text-green-800' :
                    statement.sentiment_score < -0.3 ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    감성 점수: {statement.sentiment_score.toFixed(2)}
                  </span>
                </div>
              </div>
              <p className="text-gray-700 whitespace-pre-wrap">
                {statement.content}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SessionDetail; 