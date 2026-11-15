import React from 'react';
import { useOutletContext, useParams, useNavigate } from 'react-router-dom';
import { useProjects } from '../../hooks/useResources';
import { ResourceLoading, ResourceNotFound } from '../../components/ResourceRouteState';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const ProjectsPage = () => {
    const context = useOutletContext();
    const { id } = useParams();
    const navigate = useNavigate();
    const projectsHook = useProjects();

    const handleSelectProject = (projectId) => {
        navigate(`/projects/${projectId}`);
    };

    const handleBack = () => {
        navigate('/projects');
    };

    if (id) {
        const selectedProject = projectsHook.projects.find(p => String(p.id) === String(id));

        if (!selectedProject) {
            if (projectsHook.loading) {
                return <ResourceLoading message="Loading project..." />;
            }
            return (
                <ResourceNotFound
                    title="Project Not Found"
                    description="The requested project could not be found or may have been deleted."
                    onBack={handleBack}
                />
            );
        }

        return (
            <ServiceView
                context={context}
                selectedProjectId={selectedProject.id}
                selectedProject={selectedProject}
                onBack={handleBack}
                projectsHook={projectsHook}
            />
        );
    }

    return (
        <ListingView
            context={context}
            projectsHook={projectsHook}
            onSelectProject={handleSelectProject}
        />
    );
};

export default ProjectsPage;
