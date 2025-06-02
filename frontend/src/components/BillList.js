import React from 'react';
import BillCard from './BillCard';

const BillList = () => {
  const bills = [
    {
      id: 1,
      status: '진행 중',
      number: '의안 1',
      title: '의안 제목 1',
      description: '의안에 대한 상세 설명입니다.',
      partyOpinions: [
        { party: '정당 A', opinion: '찬성' },
        { party: '정당 B', opinion: '반대' },
      ],
    },
    {
      id: 2,
      status: '완료',
      number: '의안 2',
      title: '의안 제목 2',
      description: '의안에 대한 상세 설명입니다.',
      partyOpinions: [
        { party: '정당 A', opinion: '찬성' },
        { party: '정당 B', opinion: '찬성' },
      ],
    },
  ];

  return (
    <section className="py-20 bg-white">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold text-gray-900 mb-6">
            대표 의안 목록
          </h2>
          <p className="text-xl text-gray-600 mb-12">
            각 의안에 대한 기본 정보와 입장 변화를 확인할 수 있습니다.
          </p>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {bills.map((bill) => (
              <BillCard
                key={bill.id}
                status={bill.status}
                number={bill.number}
                title={bill.title}
                description={bill.description}
                partyOpinions={bill.partyOpinions}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default BillList; 