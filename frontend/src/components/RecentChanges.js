import React from 'react';
import ChangeArticle from './ChangeArticle';

const RecentChanges = () => {
  const changes = [
    {
      id: 1,
      title: '의안 제목 1',
      party: '정당 A의 입장',
      description: '상세 분석 내용입니다.',
      image: '/images/change1.jpg',
    },
    {
      id: 2,
      title: '의안 제목 2',
      party: '정당 B의 입장',
      description: '상세 분석 내용입니다.',
      image: '/images/change2.jpg',
    },
  ];

  return (
    <section className="py-20 bg-gray-50">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold text-gray-900 mb-6">
            최근 의안 변화
          </h2>
          <p className="text-xl text-gray-600 mb-12">
            정당별 의안별 입장 변화를 시각적으로 보여줍니다.
          </p>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {changes.map((change) => (
              <ChangeArticle
                key={change.id}
                title={change.title}
                party={change.party}
                description={change.description}
                image={change.image}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default RecentChanges; 