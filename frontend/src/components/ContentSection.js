
import React from 'react';
import { Link } from 'react-router-dom';

const ContentSection = ({ title, description, buttonText, buttonLink, children }) => {
  return (
    <section className="flex overflow-hidden flex-col justify-center px-20 py-24 w-full bg-white max-md:px-5 max-md:max-w-full">
      <div className="flex flex-col w-full max-md:max-w-full">
        <div className="flex flex-wrap gap-10 justify-between items-center w-full max-md:max-w-full">
          <div className="flex flex-col self-stretch my-auto min-w-[240px] w-[626px] max-md:max-w-full">
            <h2 className="text-4xl font-bold leading-none text-black max-md:max-w-full">
              {title}
            </h2>
            <p className="mt-4 text-xl leading-7 text-gray-600 max-md:max-w-full">
              {description}
            </p>
          </div>
          {buttonText && buttonLink && (
            <Link
              to={buttonLink}
              className="gap-2 self-stretch px-6 py-3 my-auto text-base font-medium leading-6 text-white bg-blue-600 rounded-lg border border-blue-600 border-solid min-h-[44px] hover:bg-blue-700 transition-colors"
            >
              {buttonText}
            </Link>
          )}
        </div>
        <div className="mt-16 w-full max-md:mt-10 max-md:max-w-full">
          {children}
        </div>
      </div>
    </section>
  );
};

export default ContentSection;
