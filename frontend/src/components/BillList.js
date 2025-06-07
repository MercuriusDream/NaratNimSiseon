import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

const BillList = ({ filter }) => {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({});
  const [currentPage, setCurrentPage] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    fetchBills();
  }, [filter, currentPage]);

  const fetchBills = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: currentPage
      });

      if (filter && filter !== 'all') {
        params.append('name', filter);
      }

      const response = await api.get(`/api/bills/?${params}`);
      setBills(response.data.results || response.data);
      setPagination({
        count: response.data.count,
        next: response.data.next,
        previous: response.data.previous
      });
    } catch (err) {
      setError('의안 목록을 불러오는 중 오류가 발생했습니다.');
      console.error('Error fetching bills:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Bill list rendering logic */}
      {loading && <p>Loading bills...</p>}
      {error && <p>Error: {error}</p>}
      {bills && bills.map(bill => (
        <div key={bill.id}>
          {bill.name}
        </div>
      ))}

        {/* Pagination */}
        {pagination.count > 10 && (
          <div className="flex justify-center space-x-2 mt-8">
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={!pagination.previous}
              className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              이전
            </button>
            <span className="px-4 py-2 text-gray-700">
              페이지 {currentPage} / {Math.ceil(pagination.count / 10)}
            </span>
            <button
              onClick={() => setCurrentPage(prev => prev + 1)}
              disabled={!pagination.next}
              className="px-4 py-2 border border-gray-300 rounded-md bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              다음
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default BillList;