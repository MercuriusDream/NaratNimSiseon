import React from 'react';

const ChangeArticle = ({ title, party, description, image }) => {
  return (
    <article className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow">
      <div className="flex flex-col md:flex-row">
        <div className="md:w-1/3">
          <img
            src={image}
            alt={title}
            className="w-full h-48 md:h-full object-cover"
          />
        </div>
        <div className="p-6 md:w-2/3">
          <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>
          <p className="text-sm text-blue-600 font-medium mb-3">{party}</p>
          <p className="text-gray-600">{description}</p>
        </div>
      </div>
    </article>
  );
};

export default ChangeArticle; 