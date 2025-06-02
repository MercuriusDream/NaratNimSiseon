import React from 'react';

const BillCard = ({ status, number, title }) => {
  return (
    <article className="overflow-hidden flex-1 shrink rounded-md border border-solid basis-0 border-black border-opacity-10">
      <div className="flex overflow-hidden w-full text-xs leading-none min-h-60">
        <div className="flex flex-col flex-1 shrink pr-12 pb-28 w-full basis-0 bg-zinc-300 bg-opacity-50 max-md:pb-24">
          <span className="self-start px-2 py-1 font-medium rounded-md bg-black bg-opacity-10">
            {status}
          </span>
          <h3 className="self-center mt-24 text-center max-md:mt-10">
            {number}
          </h3>
        </div>
      </div>
      <div className="p-3 w-full">
        <h4 className="text-base">{title}</h4>
        <p className="mt-1 text-xl font-medium leading-snug">
          정당별 의견 변화
        </p>
      </div>
    </article>
  );
};

export default BillCard; 