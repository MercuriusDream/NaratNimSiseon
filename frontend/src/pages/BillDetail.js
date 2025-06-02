import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import SentimentChart from '../components/SentimentChart';

function BillDetail() {
  const { id } = useParams();
  const [bill, setBill] = useState(null);
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBillData = async () => {
      try {
        setLoading(true);
        const [billRes, statementsRes] = await Promise.all([
          axios.get(`/api/bills/${id}/`),
          axios.get(`/api/bills/${id}/statements/`)
        ]);
        
        setBill(billRes.data);
        setStatements(statementsRes.data);
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
    <div className="container mx-auto px-4 py-8">
      {/* Bill Header */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h1 className="text-3xl font-bold mb-4">{bill.bill_name}</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">의안번호:</span>{' '}
              {bill.bill_no}
            </p>
            <p className="text-gray-600">
              <span className="font-semibold">제안자:</span>{' '}
              {bill.proposer}
            </p>
          </div>
          <div>
            <p className="text-gray-600">
              <span className="font-semibold">제안일:</span>{' '}
              {new Date(bill.propose_dt).toLocaleDateString('ko-KR')}
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
                 '대기중'}
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* Bill Content */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">의안 내용</h2>
        <div className="prose max-w-none">
          <p className="whitespace-pre-wrap">{bill.content}</p>
        </div>
      </div>

      {/* Sentiment Analysis */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-2xl font-bold mb-4">감성 분석 결과</h2>
        <SentimentChart data={statements} />
      </div>

      {/* Related Statements */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-4">관련 발언</h2>
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

export default BillDetail; 