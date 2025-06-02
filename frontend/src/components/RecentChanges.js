import React, { useState, useEffect } from 'react';
import ChangeArticle from './ChangeArticle';

const RecentChanges = () => {
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchChanges = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/bills/?ordering=-updated_at&page_size=3');
        if (!response.ok) throw new Error('최근 변화를 불러오는데 실패했습니다.');
        const data = await response.json();
        setChanges(data.results || []);
      } catch (err) {
        setError(err.message);
        console.error('Error fetching recent changes:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchChanges();
  }, []);

  if (loading) {
    return (
      <section className="py-20 bg-gray-50">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">최근 변화를 불러오는 중...</p>
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="py-20 bg-gray-50">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <p className="text-red-600">{error}</p>
            <button onClick={() => window.location.reload()} className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">다시 시도</button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="py-20 bg-gray-50">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold text-gray-900 mb-6">최근 의안 변화</h2>
          <p className="text-xl text-gray-600 mb-12">정당별 의안별 입장 변화를 시각적으로 보여줍니다.</p>
          {changes.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600">표시할 최근 변화가 없습니다.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {changes.map((change) => (
                <ChangeArticle
                  key={change.id}
                  title={change.bill_nm}
                  party={change.proposer}
                  description={change.summary || ''}
                  image={change.image || '/default-bill.png'}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default RecentChanges; 