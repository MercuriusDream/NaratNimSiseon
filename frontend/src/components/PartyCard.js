
import React from 'react';
import { Link } from 'react-router-dom';

const PartyCard = ({ id, image, title, subtitle, description }) => {
  return (
    <Link 
      to={`/parties/${id}`}
      className="flex flex-col min-w-[240px] w-[300px] hover:shadow-lg transition-shadow"
    >
      <div className="flex flex-col w-full">
        <div className="flex overflow-hidden flex-col justify-center items-center px-20 py-16 w-full bg-gray-50 rounded-lg max-md:px-5">
          <img
            loading="lazy"
            src={image}
            alt={`${title} 로고`}
            className="object-contain w-20 aspect-square"
          />
        </div>
        <div className="flex flex-col mt-6 w-full">
          <div className="flex flex-col w-full">
            <h3 className="text-lg font-semibold leading-7 text-gray-900">
              {title}
            </h3>
            {subtitle && (
              <p className="mt-1 text-base leading-6 text-gray-600">
                {subtitle}
              </p>
            )}
          </div>
          {description && (
            <p className="mt-2 text-base leading-6 text-gray-600">
              {description}
            </p>
          )}
        </div>
      </div>
    </Link>
  );
};

export default PartyCard;
