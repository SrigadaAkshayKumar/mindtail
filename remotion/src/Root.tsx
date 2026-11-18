import React from 'react';
import {Composition} from 'remotion';
import {Clip, ClipProps} from './Clip';

// One composition. Everything (video file, camera, captions, colours) comes in as props
// from the python side (clipper/edit.py --engine remotion), so both engines share one plan.
export const Root: React.FC = () => (
  <Composition
    id="Clip"
    component={Clip}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={30}
    defaultProps={{} as ClipProps}
    calculateMetadata={({props}) => ({durationInFrames: Math.max(1, props.frames ?? 30), fps: props.fps ?? 30})}
  />
);
