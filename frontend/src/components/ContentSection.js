
import React from 'react';

const ContentSection = ({ title, description, buttonText, buttonLink, children }) => {
  return (
    <section className="flex overflow-hidden flex-col px-20 py-16 w-full bg-white max-md:px-5 max-md:py-12 max-md:max-w-full">
      <div className="flex flex-col w-full max-w-6xl mx-auto">
        <div className="flex flex-wrap gap-5 justify-between items-end mb-12 max-md:max-w-full">
          <div className="flex flex-col max-md:max-w-full">
            <h2 className="text-4xl font-bold text-slate-800 leading-tight max-md:text-3xl mb-4">
              {title}
            </h2>
            <p className="text-lg text-slate-600 leading-relaxed max-w-2xl">
              {description}
            </p>
          </div>
          {buttonText && buttonLink && (
            <a
              href={buttonLink}
              className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors duration-200 min-w-fit"
            >
              {buttonText}
            </a>
          )}
        </div>
        <div className="w-full">
          {children}
        </div>
      </div>
    </section>
  );
};

export default ContentSection;
