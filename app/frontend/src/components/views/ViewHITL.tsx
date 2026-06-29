import React from 'react';
import { CheckSquareOffset } from '@phosphor-icons/react';

import { PageFrame } from '../ui';
import KbV2AdminWorkspace from './KbV2AdminWorkspace';

export default function ViewHITL({ activeView }: { activeView: string }) {
    return (
        <PageFrame
            id="view-hitl"
            active={activeView === 'view-hitl'}
            icon={CheckSquareOffset}
            title="Duyệt văn bản"
            description=""
        >
            <KbV2AdminWorkspace />
        </PageFrame>
    );
}
