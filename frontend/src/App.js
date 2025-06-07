import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';

// Pages
import Home from './pages/Home';
import PartyList from './pages/PartyList';
import PartyDetail from './pages/PartyDetail';
import SessionList from './pages/SessionList';
import SessionDetail from './pages/SessionDetail';
import BillList from './pages/BillList';
import BillDetail from './pages/BillDetail';
import SpeakerList from './pages/SpeakerList';
import SpeakerDetail from './pages/SpeakerDetail';
import PartyList from './pages/PartyList';
import PartyDetail from './pages/PartyDetail';
import SentimentAnalysis from './pages/SentimentAnalysis';
import StatementList from './pages/StatementList';

function App() {
  return (
    <Router>
      <div className="App">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/parties" element={<PartyList />} />
          <Route path="/parties/:id" element={<PartyDetail />} />
          <Route path="/sentiment" element={<SentimentAnalysis />} />
          <Route path="/statements" element={<StatementList />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;