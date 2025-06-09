import React, { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import api from "../api";
import NavigationHeader from "../components/NavigationHeader";
import Footer from "../components/Footer";
import SentimentChart from "../components/SentimentChart";

function SpeakerDetail() {
  const { id } = useParams();
  const [speaker, setSpeaker] = useState(null);
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState("all"); // 'all', 'month', 'year'

  useEffect(() => {
    const fetchSpeakerData = async () => {
      try {
        setLoading(true);
        const [speakerRes, statementsRes] = await Promise.all([
          api.get(`api/speakers/${id}/`),
          api.get(`speakers/${id}/statements/?time_range=${timeRange}`),
        ]);

        setSpeaker(speakerRes.data);
        setStatements(statementsRes.data);
      } catch (err) {
        setError("데이터를 불러오는 중 오류가 발생했습니다.");
        console.error("Error fetching speaker data:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchSpeakerData();
  }, [id, timeRange]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return <div className="text-center text-red-600 p-4">{error}</div>;
  }

  if (!speaker) {
    return (
      <div className="text-center text-gray-600 p-4">
        의원 정보를 찾을 수 없습니다.
      </div>
    );
  }

  return (
    <div className="flex overflow-hidden flex-col bg-white min-h-screen">
      <NavigationHeader />
      <main className="flex flex-col w-full">
        <div className="container mx-auto px-4 py-8">
          {/* Speaker Header */}
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                {speaker.naas_pic ? (
                  <img
                    src={speaker.naas_pic}
                    alt={speaker.naas_nm}
                    className="h-20 w-20 rounded-full object-cover border border-gray-200"
                  />
                ) : (
                  <div className="h-20 w-20 rounded-full bg-gray-200 flex items-center justify-center">
                    <span className="text-3xl font-bold text-gray-500">
                      {speaker.naas_nm.charAt(0)}
                    </span>
                  </div>
                )}
              </div>
              <div className="ml-6">
                <h1 className="text-3xl font-bold">{speaker.naas_nm}</h1>
                <p className="text-lg text-gray-600">{speaker.plpt_nm}</p>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                {speaker.elecd_nm && speaker.elecd_nm.length > 0 && (
                  <p className="text-gray-600">
                    <span className="font-semibold">선거구명:</span>{" "}
                    {speaker.elecd_nm.join(", ")}
                  </p>
                )}
                {speaker.elecd_div_nm && speaker.elecd_div_nm.length > 0 && (
                  <p className="text-gray-600">
                    <span className="font-semibold">선거구 구분:</span>{" "}
                    {speaker.elecd_div_nm.join(", ")}
                  </p>
                )}
                {speaker.cmit_nm && speaker.cmit_nm.length > 0 && (
                  <p className="text-gray-600">
                    <span className="font-semibold">소속 위원회:</span>{" "}
                    {speaker.cmit_nm.join(", ")}
                  </p>
                )}
                {speaker.blng_cmit_nm && speaker.blng_cmit_nm.length > 0 && (
                  <p className="text-gray-600">
                    <span className="font-semibold">소속 상임위:</span>{" "}
                    {speaker.blng_cmit_nm.join(", ")}
                  </p>
                )}
                {speaker.gtelt_eraco && speaker.gtelt_eraco.length > 0 && (
                  <p className="text-gray-600">
                    <span className="font-semibold">역대 대수:</span>{" "}
                    {speaker.gtelt_eraco.join(", ")}
                  </p>
                )}
                {typeof speaker.era_int === "number" && (
                  <p className="text-gray-600">
                    <span className="font-semibold">대수(숫자):</span>{" "}
                    {speaker.era_int}
                  </p>
                )}
                {typeof speaker.nth_term === "number" && (
                  <p className="text-gray-600">
                    <span className="font-semibold">임기(회수):</span>{" "}
                    {speaker.nth_term}
                  </p>
                )}
              </div>
              <div>
                <p className="text-gray-600">
                  <span className="font-semibold">평균 감성 점수:</span>{" "}
                  <span
                    className={`${
                      speaker.avg_sentiment > 0.3
                        ? "text-green-600"
                        : speaker.avg_sentiment < -0.3
                          ? "text-red-600"
                          : "text-gray-600"
                    }`}
                  >
                    {speaker.avg_sentiment?.toFixed(2) || "N/A"}
                  </span>
                </p>
                <p className="text-gray-600">
                  <span className="font-semibold">총 발언 수:</span>{" "}
                  {speaker.total_statements || 0}
                </p>
              </div>
              <div>
                <p className="text-gray-600">
                  <span className="font-semibold">가결 의안 수:</span>{" "}
                  {speaker.approved_bills || 0}
                </p>
                <p className="text-gray-600">
                  <span className="font-semibold">부결 의안 수:</span>{" "}
                  {speaker.rejected_bills || 0}
                </p>
              </div>
            </div>
          </div>

          {/* Time Range Filter */}
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <div className="flex justify-center space-x-4">
              <button
                onClick={() => setTimeRange("all")}
                className={`px-4 py-2 rounded-md ${
                  timeRange === "all"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                전체
              </button>
              <button
                onClick={() => setTimeRange("year")}
                className={`px-4 py-2 rounded-md ${
                  timeRange === "year"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                최근 1년
              </button>
              <button
                onClick={() => setTimeRange("month")}
                className={`px-4 py-2 rounded-md ${
                  timeRange === "month"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                최근 1개월
              </button>
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
              {statements.map((statement) => (
                <div
                  key={statement.id}
                  className="border-b pb-6 last:border-b-0"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="text-lg font-semibold">
                        {new Date(statement.session.conf_dt).toLocaleDateString(
                          "ko-KR",
                        )}
                      </h3>
                      <p className="text-sm text-gray-600">
                        {statement.session.era_co}대 {statement.session.sess}회{" "}
                        {statement.session.dgr}차
                      </p>
                    </div>
                    <div className="text-sm">
                      <span
                        className={`px-2 py-1 rounded ${
                          statement.sentiment_score > 0.3
                            ? "bg-green-100 text-green-800"
                            : statement.sentiment_score < -0.3
                              ? "bg-red-100 text-red-800"
                              : "bg-gray-100 text-gray-800"
                        }`}
                      >
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
      </main>
      <Footer />
    </div>
  );
}

export default SpeakerDetail;
