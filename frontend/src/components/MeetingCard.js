import React from 'react';

const MeetingCard = ({ title, date, description }) => {
  return (
    <article className="flex flex-wrap flex-1 shrink gap-4 justify-center items-start self-stretch p-4 my-auto rounded-md border border-solid basis-0 border-black border-opacity-10 min-w-60 max-md:max-w-full">
      <div className="flex overflow-hidden min-h-[100px] w-[100px]">
        <div className="flex flex-1 shrink basis-0 bg-zinc-300 bg-opacity-50 h-[100px] min-h-[100px] w-[100px]" />
      </div>
      <div className="flex-1 shrink text-black basis-0 min-w-60">
        <h3 className="text-xl font-medium leading-snug">
          {title}
        </h3>
        <p className="mt-2 text-sm leading-none text-black">
          {date}
        </p>
        <p className="mt-2 text-base">
          {description}
        </p>
      </div>
    </article>
  );
};

export default MeetingCard; 