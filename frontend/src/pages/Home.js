import React, { useEffect, useState } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import HeroSection from '../components/HeroSection';
import ContentSection from '../components/ContentSection';
import Footer from '../components/Footer';
import PartyCard from '../components/PartyCard';
import MeetingCard from '../components/MeetingCard';
import BillCard from '../components/BillCard';

const Home = () => {
  const [parties, setParties] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [partyRes, meetingRes, billRes] = await Promise.all([
          fetch('/api/parties/?page_size=4'),
          fetch('/api/sessions/?page_size=3'),
          fetch('/api/bills/?page_size=3'),
        ]);
        const partyData = await partyRes.json();
        const meetingData = await meetingRes.json();
        const billData = await billRes.json();
        setParties(partyData.results || []);
        setMeetings(meetingData.results || []);
        setBills(billData.results || []);
      } catch (err) {
        setError('데이터를 불러오는 중 오류가 발생했습니다.');
        console.error('Error fetching home data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <main className="relative pt-20 bg-white min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="relative pt-20 bg-white min-h-screen flex items-center justify-center">
        <div className="text-red-600">{error}</div>
      </main>
    );
  }

  return (
    <main className="relative pt-20 bg-white">
      <NavigationHeader />
      <HeroSection />

      <ContentSection
        title="주요 정당 소개"
        description="시민들이 알아야 할 정당들입니다."
        buttonText="모든 정당 보기"
      >
        <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
          {parties.map((party) => (
            <PartyCard
              key={party.id}
              image={party.logo_url || '/default-party.png'}
              title={party.name}
              subtitle={party.slogan || ''}
              description={party.description || ''}
            />
          ))}
        </div>
      </ContentSection>

      <ContentSection
        title="최근 회의록"
        description="정치의 최신 동향을 확인하세요."
        buttonText="모든 회의록 보기"
      >
        <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
          {meetings.map((meeting) => (
            <MeetingCard
              key={meeting.id}
              title={meeting.title || meeting.conf_nm}
              date={meeting.conf_dt}
              description={meeting.summary || ''}
            />
          ))}
        </div>
      </ContentSection>

      <ContentSection
        title="최근 의안"
        description="주요 의안을 확인해보세요."
        buttonText="모든 의안 보기"
      >
        <div className="flex flex-wrap gap-10 items-center w-full max-md:max-w-full">
          {bills.map((bill) => (
            <BillCard
              key={bill.id}
              title={bill.bill_nm}
              date={bill.proposal_date}
              description={bill.summary || ''}
            />
          ))}
        </div>
      </ContentSection>

      <Footer />
    </main>
  );
};

export default Home;
