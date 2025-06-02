import React from 'react';
import TopNavigation from '../components/TopNavigation';
import HeroSection from '../components/HeroSection';
import BillList from '../components/BillList';
import RecentChanges from '../components/RecentChanges';
import DataMetrics from '../components/DataMetrics';
import Footer from '../components/Footer';

const BillListPage = () => {
  return (
    <div className="relative pt-20 bg-white">
      <TopNavigation />
      <main>
        <HeroSection />
        <BillList />
        <RecentChanges />
        <DataMetrics />
      </main>
      <Footer />
    </div>
  );
};

export default BillListPage;